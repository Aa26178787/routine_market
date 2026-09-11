import hashlib
import os
from datetime import timedelta
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from apps.accounts.models import User
from apps.orders.models import Cart, CartItem, DownloadLog, Order, OrderItem
from apps.orders.services import complete_virtual_payment, create_order_from_cart
from apps.products.models import (
    Category,
    ExerciseGoal,
    Product,
    ProductFile,
    WishlistItem,
)
from apps.reviews.models import Review
from apps.trainers.models import Certification, TrainerApplication, TrainerProfile


DEMO_PASSWORD = "RoutineDemo123!"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _upsert_user(*, email, full_name, nickname, password, **flags):
    user, _ = User.objects.get_or_create(email=email)
    user.full_name = full_name
    user.nickname = nickname
    user.is_active = True
    for name, value in flags.items():
        setattr(user, name, value)
    user.set_password(password)
    user.save()
    return user


def _save_if_missing(key, content):
    if not default_storage.exists(key):
        default_storage.save(key, ContentFile(content))
    return key


def _thumbnail_bytes(*, primary, accent):
    image = Image.new("RGB", (1200, 675), primary)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((90, 90, 1110, 585), radius=48, fill=accent)
    draw.ellipse((150, 170, 430, 450), fill=primary)
    draw.rectangle((520, 190, 990, 240), fill=primary)
    draw.rectangle((520, 290, 900, 340), fill=primary)
    draw.rectangle((520, 390, 800, 440), fill=primary)
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _xlsx_bytes(*, title, rows):
    def cell(column, row_number, value):
        if isinstance(value, int):
            return f'<c r="{column}{row_number}"><v>{value}</v></c>'
        escaped = (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        return (
            f'<c r="{column}{row_number}" t="inlineStr">'
            f"<is><t>{escaped}</t></is></c>"
        )

    all_rows = [("주차", "운동", "세트", "반복/시간", "메모"), *rows]
    sheet_rows = []
    for row_number, values in enumerate(all_rows, start=1):
        cells = "".join(
            cell(chr(65 + index), row_number, value)
            for index, value in enumerate(values)
        )
        sheet_rows.append(f'<row r="{row_number}">{cells}</row>')

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
    workbook = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="{title}" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""
    sheet = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>{''.join(sheet_rows)}</sheetData>
</worksheet>"""

    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return output.getvalue()


def _pdf_bytes():
    stream = (
        b"BT /F1 18 Tf 72 760 Td (Routine Market Demo Certification) Tj "
        b"0 -30 Td /F1 11 Tf (For local development and presentation only.) Tj ET"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length " + str(len(stream)).encode() + b">>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    document = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{number} 0 obj\n".encode())
        document.extend(body)
        document.extend(b"\nendobj\n")
    xref_offset = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode())
    document.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return bytes(document)


class Command(BaseCommand):
    help = "개발·시연용 사용자, 상품, 주문과 리뷰를 반복 실행 가능하게 구성합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="데모 계정의 주문·리뷰·장바구니·찜을 초기 시연 상태로 되돌립니다.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("보호를 위해 DEBUG=true인 환경에서만 실행할 수 있습니다.")

        password = os.getenv("DEMO_PASSWORD", DEMO_PASSWORD)
        now = timezone.now()

        with transaction.atomic():
            if options["reset"]:
                demo_orders = Order.objects.filter(
                    buyer__email="buyer@routine-market.local"
                )
                demo_items = OrderItem.objects.filter(order__in=demo_orders)
                DownloadLog.objects.filter(order_item__in=demo_items).delete()
                Review.objects.filter(order_item__in=demo_items).delete()
                demo_items.delete()
                demo_orders.delete()
                CartItem.objects.filter(
                    cart__user__email="buyer@routine-market.local"
                ).delete()
                WishlistItem.objects.filter(
                    user__email="buyer@routine-market.local"
                ).delete()

            admin = _upsert_user(
                email="admin@routine-market.local",
                full_name="루틴마켓 관리자",
                nickname="관리자",
                password=password,
                is_staff=True,
                is_superuser=True,
            )
            trainer_user = _upsert_user(
                email="trainer@routine-market.local",
                full_name="김루틴",
                nickname="루틴코치",
                password=password,
                role=User.Role.TRAINER,
                is_staff=False,
                is_superuser=False,
            )
            buyer = _upsert_user(
                email="buyer@routine-market.local",
                full_name="이운동",
                nickname="운동초보",
                password=password,
                role=User.Role.MEMBER,
                is_staff=False,
                is_superuser=False,
            )
            pending_user = _upsert_user(
                email="pending@routine-market.local",
                full_name="박트레이너",
                nickname="승인대기코치",
                password=password,
                role=User.Role.MEMBER,
                is_staff=False,
                is_superuser=False,
            )

            approved_application, _ = TrainerApplication.objects.update_or_create(
                user=trainer_user,
                defaults={
                    "specialty": "근력 운동",
                    "career_years": 7,
                    "career_description": "생활체육과 웨이트 트레이닝 지도 경력 7년",
                    "introduction": "지속 가능한 운동 습관을 설계하는 트레이너입니다.",
                    "activity_url": "https://example.com/routine-coach",
                    "status": TrainerApplication.Status.APPROVED,
                    "rejection_reason": "",
                    "reviewed_by": admin,
                    "submitted_at": now - timedelta(days=20),
                    "reviewed_at": now - timedelta(days=19),
                },
            )
            trainer, _ = TrainerProfile.objects.update_or_create(
                user=trainer_user,
                defaults={
                    "specialty": approved_application.specialty,
                    "career_years": approved_application.career_years,
                    "introduction": approved_application.introduction,
                    "activity_url": approved_application.activity_url,
                    "is_verified": True,
                    "verified_at": approved_application.reviewed_at,
                },
            )

            pending_application, _ = TrainerApplication.objects.update_or_create(
                user=pending_user,
                defaults={
                    "specialty": "러닝",
                    "career_years": 3,
                    "career_description": "5K·10K 입문자 러닝 지도 경력 3년",
                    "introduction": "부상 없이 달리는 습관을 돕고 싶습니다.",
                    "activity_url": "https://example.com/pending-coach",
                    "status": TrainerApplication.Status.PENDING,
                    "rejection_reason": "",
                    "reviewed_by": None,
                    "submitted_at": now - timedelta(days=1),
                    "reviewed_at": None,
                },
            )
            evidence_key = _save_if_missing(
                "demo/certifications/pending-trainer-v2.pdf", _pdf_bytes()
            )
            Certification.objects.update_or_create(
                application=pending_application,
                name="생활스포츠지도사 2급",
                defaults={
                    "issuer": "문화체육관광부",
                    "country_code": "KR",
                    "credential_number": "DEMO-2026-001",
                    "evidence_object_key": evidence_key,
                    "original_filename": "demo-certification.pdf",
                },
            )

            product_specs = [
                {
                    "slug": "demo-8week-strength",
                    "title": "초보자를 위한 8주 근력 루틴",
                    "short_description": "기초 동작부터 점진적으로 강도를 높이는 8주 프로그램",
                    "description": "헬스장 입문자가 주 3회 따라 할 수 있는 전신 근력 루틴입니다.",
                    "category": "bodybuilding",
                    "goals": ["strength", "muscle-gain"],
                    "difficulty": Product.Difficulty.BEGINNER,
                    "weeks": 8,
                    "sessions": 3,
                    "price": 19000,
                    "colors": ("#182433", "#7CE4B6"),
                    "rows": [(1, "스쿼트", 3, "10회", "가벼운 중량"), (1, "푸시업", 3, "8회", "무릎 대고 가능")],
                },
                {
                    "slug": "demo-5k-running",
                    "title": "첫 5K 완주 러닝 플랜",
                    "short_description": "걷기와 달리기를 조합해 5K 완주를 준비하는 프로그램",
                    "description": "러닝 초보자를 위한 주 4회, 6주 단계별 훈련 계획입니다.",
                    "category": "running",
                    "goals": ["fitness", "stress-relief"],
                    "difficulty": Product.Difficulty.BEGINNER,
                    "weeks": 6,
                    "sessions": 4,
                    "price": 15000,
                    "colors": ("#1D3557", "#F4A261"),
                    "rows": [(1, "걷기+조깅", 1, "30분", "대화 가능한 강도"), (2, "이지런", 1, "25분", "천천히 달리기")],
                },
                {
                    "slug": "demo-home-mobility",
                    "title": "하루 20분 홈트와 모빌리티",
                    "short_description": "장비 없이 집에서 진행하는 근력·유연성 프로그램",
                    "description": "바쁜 일상에서도 실천할 수 있는 주 5회 홈트레이닝 루틴입니다.",
                    "category": "home-training",
                    "goals": ["weight-loss", "body-shape"],
                    "difficulty": Product.Difficulty.INTERMEDIATE,
                    "weeks": 4,
                    "sessions": 5,
                    "price": 12000,
                    "colors": ("#312244", "#C77DFF"),
                    "rows": [(1, "버드독", 3, "좌우 10회", "허리 중립"), (1, "런지", 3, "좌우 12회", "무릎 정렬")],
                },
            ]

            products = []
            for spec in product_specs:
                thumbnail_key = _save_if_missing(
                    f"demo/product-thumbnails/{spec['slug']}.png",
                    _thumbnail_bytes(primary=spec["colors"][0], accent=spec["colors"][1]),
                )
                product, _ = Product.objects.update_or_create(
                    slug=spec["slug"],
                    defaults={
                        "seller": trainer,
                        "category": Category.objects.get(slug=spec["category"]),
                        "title": spec["title"],
                        "short_description": spec["short_description"],
                        "description": spec["description"],
                        "difficulty": spec["difficulty"],
                        "duration_weeks": spec["weeks"],
                        "sessions_per_week": spec["sessions"],
                        "price": spec["price"],
                        "thumbnail_object_key": thumbnail_key,
                        "status": Product.Status.DRAFT,
                        "published_at": now - timedelta(days=10),
                    },
                )
                product.goals.set(ExerciseGoal.objects.filter(slug__in=spec["goals"]))

                routine_bytes = _xlsx_bytes(title="운동 루틴", rows=spec["rows"])
                routine_key = _save_if_missing(
                    f"demo/routine-files/{spec['slug']}.xlsx", routine_bytes
                )
                ProductFile.objects.filter(product=product, is_current=True).exclude(
                    version=1
                ).update(is_current=False)
                ProductFile.objects.update_or_create(
                    product=product,
                    version=1,
                    defaults={
                        "object_key": routine_key,
                        "original_filename": f"{spec['slug']}.xlsx",
                        "content_type": XLSX_CONTENT_TYPE,
                        "size_bytes": len(routine_bytes),
                        "checksum_sha256": hashlib.sha256(routine_bytes).hexdigest(),
                        "is_current": True,
                    },
                )
                product.status = Product.Status.PUBLISHED
                product.full_clean()
                product.save(update_fields=["status", "updated_at"])
                products.append(product)

            purchased_item = (
                OrderItem.objects.select_related("order")
                .filter(
                    order__buyer=buyer,
                    order__status=Order.Status.PAID,
                    product=products[0],
                )
                .first()
            )
            if purchased_item is None:
                cart, _ = Cart.objects.get_or_create(user=buyer)
                CartItem.objects.get_or_create(cart=cart, product=products[0])
                order = create_order_from_cart(buyer=buyer)
                complete_virtual_payment(order_id=order.pk, buyer=buyer)
                purchased_item = order.items.get(product=products[0])

            Review.objects.update_or_create(
                order_item=purchased_item,
                defaults={
                    "author": buyer,
                    "product": products[0],
                    "rating": 5,
                    "content": "동작 설명과 주차별 강도 구성이 명확해서 꾸준히 따라가기 좋았습니다.",
                    "is_visible": True,
                },
            )
            cart, _ = Cart.objects.get_or_create(user=buyer)
            CartItem.objects.get_or_create(cart=cart, product=products[1])
            WishlistItem.objects.get_or_create(user=buyer, product=products[2])

        self.stdout.write(self.style.SUCCESS("Routine Market 데모 데이터를 구성했습니다."))
        if options["reset"]:
            self.stdout.write("데모 구매 흐름을 초기 상태로 복구했습니다.")
        self.stdout.write(f"공통 데모 비밀번호: {password}")
        self.stdout.write("관리자: admin@routine-market.local")
        self.stdout.write("구매자: buyer@routine-market.local")
        self.stdout.write("트레이너: trainer@routine-market.local")
        self.stdout.write("승인 대기: pending@routine-market.local")
