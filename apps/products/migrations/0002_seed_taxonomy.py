from django.db import migrations


CATEGORIES = [
    ("보디빌딩", "bodybuilding"),
    ("파워리프팅", "powerlifting"),
    ("크로스핏", "crossfit"),
    ("러닝", "running"),
    ("홈트레이닝", "home-training"),
    ("스트레칭", "stretching"),
]

GOALS = [
    ("근력 향상", "strength"),
    ("근육 증가", "muscle-gain"),
    ("체중 감량", "weight-loss"),
    ("체력 증진", "fitness"),
    ("체형 관리", "body-shape"),
    ("스트레스 해소", "stress-relief"),
]


def seed_taxonomy(apps, schema_editor):
    Category = apps.get_model("products", "Category")
    ExerciseGoal = apps.get_model("products", "ExerciseGoal")

    for index, (name, slug) in enumerate(CATEGORIES):
        Category.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "sort_order": index, "is_active": True},
        )
    for index, (name, slug) in enumerate(GOALS):
        ExerciseGoal.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "sort_order": index, "is_active": True},
        )


class Migration(migrations.Migration):
    dependencies = [("products", "0001_initial")]

    operations = [migrations.RunPython(seed_taxonomy, migrations.RunPython.noop)]
