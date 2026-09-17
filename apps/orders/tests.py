import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.products.models import Category, Product, ProductFile
from apps.trainers.models import TrainerProfile

from .models import Cart, CartItem, DownloadLog, Order, OrderItem
from .services import (
    complete_virtual_payment,
    confirm_toss_payment,
    create_order_from_cart,
    user_can_download,
)
from .toss_payments import TossPaymentsError


class OrderServiceTests(TestCase):
    def test_cart_uses_account_sidebar_and_marks_cart_active(self):
        self.client.force_login(self.buyer)

        response = self.client.get(reverse("orders:cart"))

        self.assertContains(response, 'aria-label="마이페이지"')
        self.assertContains(
            response,
            f'class="active" href="{reverse("orders:cart")}">장바구니</a>',
            html=False,
        )

    def test_purchase_button_uses_existing_cart_checkout_flow(self):
        self.client.force_login(self.buyer)
        response = self.client.post(
            reverse("orders:cart_add", args=[self.product.pk]),
            {"proceed": "checkout"},
        )
        self.assertRedirects(response, reverse("orders:checkout"))
        self.assertTrue(CartItem.objects.filter(cart__user=self.buyer, product=self.product).exists())
        self.assertFalse(Order.objects.filter(buyer=self.buyer).exists())

    def setUp(self):
        user_model = get_user_model()
        self.buyer = user_model.objects.create_user(
            email="buyer@example.com",
            password="safe-test-password",
            full_name="구매자",
            nickname="buyer",
        )
        seller_user = user_model.objects.create_user(
            email="seller@example.com",
            password="safe-test-password",
            full_name="판매자",
            nickname="seller",
            role=user_model.Role.TRAINER,
        )
        trainer = TrainerProfile.objects.create(
            user=seller_user,
            specialty="러닝",
            career_years=5,
            introduction="러닝 코치",
            is_verified=True,
            verified_at=timezone.now(),
        )
        category, _ = Category.objects.get_or_create(name="러닝", defaults={"slug": "running"})
        self.product = Product.objects.create(
            seller=trainer,
            category=category,
            title="10K 러닝 루틴",
            slug="10k-running",
            short_description="10K 완주 프로그램",
            description="8주 러닝 프로그램",
            difficulty=Product.Difficulty.INTERMEDIATE,
            duration_weeks=8,
            sessions_per_week=4,
            price=15000,
            thumbnail_object_key="thumbnails/running.png",
            status=Product.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        ProductFile.objects.create(
            product=self.product,
            version=1,
            object_key="routines/running-v1.xlsx",
            original_filename="running.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            size_bytes=200,
            checksum_sha256="c" * 64,
            is_current=True,
        )
        cart = Cart.objects.create(user=self.buyer)
        CartItem.objects.create(cart=cart, product=self.product)

    def test_order_keeps_price_and_file_snapshot(self):
        order = create_order_from_cart(buyer=self.buyer)
        item = order.items.get()

        self.product.price = 20000
        self.product.save(update_fields=["price"])

        item.refresh_from_db()
        self.assertEqual(order.total_amount, 15000)
        self.assertEqual(item.unit_price, 15000)
        self.assertEqual(item.product_file.version, 1)

    def test_payment_is_idempotent_and_grants_download(self):
        order = create_order_from_cart(buyer=self.buyer)

        first = complete_virtual_payment(order_id=order.pk, buyer=self.buyer)
        second = complete_virtual_payment(order_id=order.pk, buyer=self.buyer)
        item = OrderItem.objects.get(order=order)

        self.assertEqual(first.status, Order.Status.PAID)
        self.assertEqual(second.status, Order.Status.PAID)
        self.assertEqual(OrderItem.objects.filter(order=order).count(), 1)
        self.assertTrue(user_can_download(user=self.buyer, order_item=item))
        self.assertFalse(CartItem.objects.filter(cart__user=self.buyer).exists())

    @patch("apps.orders.services.TossPaymentsClient.confirm")
    def test_toss_payment_is_idempotent_and_keeps_paid_timestamp(self, confirm):
        order = create_order_from_cart(buyer=self.buyer)
        payment_key = "test-payment-key"
        confirm.return_value = {
            "status": "DONE",
            "orderId": str(order.order_number),
            "paymentKey": payment_key,
            "totalAmount": order.total_amount,
            "method": "카드",
            "receipt": {"url": "https://example.com/receipt"},
        }

        first = confirm_toss_payment(
            order_id=order.pk,
            buyer=self.buyer,
            payment_key=payment_key,
            toss_order_id=str(order.order_number),
            amount=order.total_amount,
        )
        second = confirm_toss_payment(
            order_id=order.pk,
            buyer=self.buyer,
            payment_key=payment_key,
            toss_order_id=str(order.order_number),
            amount=order.total_amount,
        )

        self.assertEqual(first.status, Order.Status.PAID)
        self.assertEqual(second.paid_at, first.paid_at)
        self.assertEqual(second.payment_provider, "TOSS_PAYMENTS")
        self.assertEqual(second.payment_method, "카드")
        self.assertEqual(second.payment_receipt_url, "https://example.com/receipt")
        confirm.assert_called_once()
        self.assertEqual(OrderItem.objects.filter(order=order).count(), 1)

    @patch("apps.orders.services.TossPaymentsClient.confirm")
    def test_checkout_toss_payment_and_purchase_history_flow(self, confirm):
        self.client.force_login(self.buyer)

        response = self.client.post(reverse("orders:checkout"))
        order = Order.objects.get(buyer=self.buyer)

        self.assertRedirects(
            response, reverse("orders:detail", args=[order.order_number])
        )
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertFalse(CartItem.objects.filter(cart__user=self.buyer).exists())

        payment_key = "test-payment-key-flow"
        confirm.return_value = {
            "status": "DONE",
            "orderId": str(order.order_number),
            "paymentKey": payment_key,
            "totalAmount": order.total_amount,
            "method": "카드",
            "receipt": None,
        }
        response = self.client.get(
            reverse("orders:toss_success", args=[order.order_number]),
            {
                "paymentKey": payment_key,
                "orderId": str(order.order_number),
                "amount": order.total_amount,
            },
        )
        order.refresh_from_db()

        self.assertRedirects(
            response, reverse("orders:detail", args=[order.order_number])
        )
        self.assertEqual(order.status, Order.Status.PAID)
        history = self.client.get(reverse("orders:purchase_history"))
        self.assertContains(history, self.product.title)

    def test_payment_page_requires_server_configuration(self):
        order = create_order_from_cart(buyer=self.buyer)
        self.client.force_login(self.buyer)

        with self.settings(
            TOSS_PAYMENTS_ENABLED=False,
            TOSS_PAYMENTS_CLIENT_KEY="",
            TOSS_PAYMENTS_SECRET_KEY="",
        ):
            response = self.client.get(reverse("orders:pay", args=[order.order_number]))

        self.assertRedirects(
            response, reverse("orders:detail", args=[order.order_number])
        )

    def test_payment_page_exposes_client_key_but_not_secret_key(self):
        order = create_order_from_cart(buyer=self.buyer)
        self.client.force_login(self.buyer)

        with self.settings(
            TOSS_PAYMENTS_ENABLED=True,
            TOSS_PAYMENTS_CLIENT_KEY="test_gck_example",
            TOSS_PAYMENTS_SECRET_KEY="test_gsk_never-expose",
        ):
            response = self.client.get(reverse("orders:pay", args=[order.order_number]))

        self.assertContains(response, "test_gck_example")
        self.assertNotContains(response, "test_gsk_never-expose")
        self.assertContains(response, "js.tosspayments.com/v2/standard")
        self.assertContains(response, "widgets.renderPaymentWindow()")

    @patch("apps.orders.services.TossPaymentsClient.confirm")
    def test_toss_amount_mismatch_is_rejected_before_confirmation(self, confirm):
        order = create_order_from_cart(buyer=self.buyer)
        self.client.force_login(self.buyer)

        response = self.client.get(
            reverse("orders:toss_success", args=[order.order_number]),
            {
                "paymentKey": "test-payment-key",
                "orderId": str(order.order_number),
                "amount": order.total_amount - 1,
            },
        )
        order.refresh_from_db()

        self.assertRedirects(
            response, reverse("orders:detail", args=[order.order_number])
        )
        self.assertEqual(order.status, Order.Status.PENDING)
        confirm.assert_not_called()

    @patch("apps.orders.services.TossPaymentsClient.confirm")
    def test_toss_api_failure_keeps_order_pending(self, confirm):
        order = create_order_from_cart(buyer=self.buyer)
        self.client.force_login(self.buyer)
        confirm.side_effect = TossPaymentsError(
            "PAYMENT_SERVICE_UNAVAILABLE", "결제 서비스 연결이 원활하지 않습니다."
        )

        response = self.client.get(
            reverse("orders:toss_success", args=[order.order_number]),
            {
                "paymentKey": "test-payment-key",
                "orderId": str(order.order_number),
                "amount": order.total_amount,
            },
        )
        order.refresh_from_db()

        self.assertRedirects(
            response, reverse("orders:detail", args=[order.order_number])
        )
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_purchase_history_is_paginated_by_six_orders(self):
        for index in range(7):
            order = Order.objects.create(
                buyer=self.buyer,
                status=Order.Status.PAID,
                total_amount=self.product.price,
                paid_at=timezone.now(),
            )
            OrderItem.objects.create(
                order=order,
                product=self.product,
                product_file=self.product.files.get(is_current=True),
                seller=self.product.seller,
                product_title=f"구매 루틴 {index}",
                seller_name=self.product.seller.user.nickname,
                unit_price=self.product.price,
            )
        self.client.force_login(self.buyer)

        first_page = self.client.get(reverse("orders:purchase_history"))
        second_page = self.client.get(
            reverse("orders:purchase_history"), {"page": 2}
        )

        self.assertEqual(len(first_page.context["orders"]), 6)
        self.assertEqual(len(second_page.context["orders"]), 1)

    def test_cancelled_order_returns_available_product_to_cart(self):
        order = create_order_from_cart(buyer=self.buyer)
        self.client.force_login(self.buyer)

        self.client.post(reverse("orders:cancel", args=[order.order_number]))
        order.refresh_from_db()

        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertTrue(
            CartItem.objects.filter(cart__user=self.buyer, product=self.product).exists()
        )

    def test_paid_buyer_can_download_and_request_is_logged(self):
        order = create_order_from_cart(buyer=self.buyer)
        complete_virtual_payment(order_id=order.pk, buyer=self.buyer)
        item = order.items.select_related("product_file").get()

        with tempfile.TemporaryDirectory() as media_root, self.settings(
            MEDIA_ROOT=media_root,
            PRIVATE_FILE_DELIVERY="proxy",
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage"
                },
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
                },
            },
        ):
            key = default_storage.save("routine-files/test.xlsx", ContentFile(b"xlsx-content"))
            item.product_file.object_key = key
            item.product_file.save(update_fields=["object_key"])
            self.client.force_login(self.buyer)

            response = self.client.get(
                reverse("orders:download", args=[item.pk]),
                HTTP_USER_AGENT="RoutineMarketTest/1.0",
            )
            body = b"".join(response.streaming_content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body, b"xlsx-content")
        log = DownloadLog.objects.get(order_item=item)
        self.assertEqual(log.user, self.buyer)
        self.assertEqual(log.user_agent, "RoutineMarketTest/1.0")

    def test_s3_download_redirect_uses_expiring_signed_url(self):
        order = create_order_from_cart(buyer=self.buyer)
        complete_virtual_payment(order_id=order.pk, buyer=self.buyer)
        item = order.items.select_related("product_file").get()
        self.client.force_login(self.buyer)

        with self.settings(PRIVATE_FILE_DELIVERY="redirect", DOWNLOAD_URL_EXPIRES=300):
            with (
                patch("apps.orders.views.default_storage.exists", return_value=True),
                patch(
                    "apps.orders.downloads.default_storage.url",
                    return_value="https://example-bucket.s3.amazonaws.com/signed-download",
                ) as storage_url,
            ):
                response = self.client.get(
                    reverse("orders:download", args=[item.pk])
                )

        self.assertRedirects(
            response,
            "https://example-bucket.s3.amazonaws.com/signed-download",
            fetch_redirect_response=False,
        )
        storage_url.assert_called_once_with(
            item.product_file.object_key,
            expire=300,
        )
        self.assertTrue(DownloadLog.objects.filter(order_item=item).exists())

    def test_other_user_cannot_download_purchase(self):
        order = create_order_from_cart(buyer=self.buyer)
        complete_virtual_payment(order_id=order.pk, buyer=self.buyer)
        item = order.items.get()
        other = get_user_model().objects.create_user(
            email="other@example.com",
            password="safe-test-password",
            full_name="다른 회원",
            nickname="other",
        )
        self.client.force_login(other)

        response = self.client.get(reverse("orders:download", args=[item.pk]))

        self.assertEqual(response.status_code, 404)
        self.assertFalse(DownloadLog.objects.exists())

    def test_missing_download_file_redirects_with_user_message_without_log(self):
        order = create_order_from_cart(buyer=self.buyer)
        complete_virtual_payment(order_id=order.pk, buyer=self.buyer)
        item = order.items.get()
        self.client.force_login(self.buyer)

        with patch("apps.orders.views.default_storage.exists", return_value=False):
            response = self.client.get(reverse("orders:download", args=[item.pk]), follow=True)

        self.assertRedirects(response, reverse("orders:purchase_history"))
        self.assertContains(response, "XLSX 파일을 불러올 수 없습니다")
        self.assertFalse(DownloadLog.objects.filter(order_item=item).exists())

    def test_storage_download_failure_redirects_without_creating_log(self):
        order = create_order_from_cart(buyer=self.buyer)
        complete_virtual_payment(order_id=order.pk, buyer=self.buyer)
        item = order.items.get()
        self.client.force_login(self.buyer)

        with (
            patch("apps.orders.views.default_storage.exists", return_value=True),
            patch("apps.orders.views.build_download_response", side_effect=OSError),
        ):
            response = self.client.get(reverse("orders:download", args=[item.pk]))

        self.assertRedirects(response, reverse("orders:purchase_history"))
        self.assertFalse(DownloadLog.objects.filter(order_item=item).exists())
