from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("products", "0003_alter_product_slug")]

    operations = [
        migrations.CreateModel(
            name="ProductDetailImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("object_key", models.CharField(max_length=500, unique=True, verbose_name="상세 이미지 객체 키")),
                ("original_filename", models.CharField(max_length=255, verbose_name="원본 파일명")),
                ("sort_order", models.PositiveSmallIntegerField(default=0, verbose_name="표시 순서")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="업로드시각")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="detail_images", to="products.product", verbose_name="상품")),
            ],
            options={
                "verbose_name": "상품 상세 이미지",
                "verbose_name_plural": "상품 상세 이미지",
                "ordering": ["sort_order", "pk"],
            },
        ),
        migrations.AddConstraint(
            model_name="productdetailimage",
            constraint=models.UniqueConstraint(fields=("product", "sort_order"), name="uniq_product_detail_image_sort_order"),
        ),
    ]
