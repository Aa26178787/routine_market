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
    ProductDetailImage,
    ProductFile,
    WishlistItem,
)
from apps.reviews.models import Review
from apps.trainers.models import Certification, TrainerApplication, TrainerProfile


DEMO_PASSWORD = "RoutineDemo123!"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DEMO_BUYER_EMAILS = [
    "buyer@routine-market.local",
    "reviewer1@routine-market.local",
    "reviewer2@routine-market.local",
    "reviewer3@routine-market.local",
    "reviewer4@routine-market.local",
]


def _upsert_user(*, email, full_name, nickname, password, **flags):
    user, _ = User.objects.get_or_create(email=email)
    user.full_name = full_name
    user.nickname = nickname
    user.is_active = True
    if user.email_verified_at is None:
        user.email_verified_at = timezone.now()
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


def _demo_thumbnail_bytes(*, filename, primary, accent):
    asset_path = (
        settings.BASE_DIR / "static" / "images" / "demo-products" / filename
    )
    if asset_path.exists():
        return asset_path.read_bytes()
    return _thumbnail_bytes(primary=primary, accent=accent)


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
                    buyer__email__in=DEMO_BUYER_EMAILS
                )
                demo_items = OrderItem.objects.filter(order__in=demo_orders)
                DownloadLog.objects.filter(order_item__in=demo_items).delete()
                Review.objects.filter(order_item__in=demo_items).delete()
                demo_items.delete()
                demo_orders.delete()
                CartItem.objects.filter(
                    cart__user__email__in=DEMO_BUYER_EMAILS
                ).delete()
                WishlistItem.objects.filter(
                    user__email__in=DEMO_BUYER_EMAILS
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
            trainers = {"strength": trainer}
            extra_trainer_specs = [
                {
                    "key": "running",
                    "email": "running.trainer@routine-market.local",
                    "full_name": "박한강",
                    "nickname": "러닝메이트",
                    "specialty": "러닝·지구력",
                    "career_years": 5,
                    "introduction": "첫 5K부터 기록 향상까지, 오래 달릴 수 있는 페이스를 함께 만듭니다.",
                },
                {
                    "key": "balance",
                    "email": "balance.trainer@routine-market.local",
                    "full_name": "이지은",
                    "nickname": "밸런스핏",
                    "specialty": "홈트레이닝·유연성",
                    "career_years": 6,
                    "introduction": "일상에서 편안하게 움직일 수 있도록 근력과 유연성을 균형 있게 지도합니다.",
                },
                {
                    "key": "crossfit",
                    "email": "crossfit.trainer@routine-market.local",
                    "full_name": "정우진",
                    "nickname": "크로스핏랩",
                    "specialty": "크로스핏·컨디셔닝",
                    "career_years": 4,
                    "introduction": "기초 동작부터 체력 향상까지 단계적으로 완성하는 기능성 운동 코치입니다.",
                },
            ]
            for spec in extra_trainer_specs:
                profile_user = _upsert_user(
                    email=spec["email"],
                    full_name=spec["full_name"],
                    nickname=spec["nickname"],
                    password=password,
                    role=User.Role.TRAINER,
                    is_staff=False,
                    is_superuser=False,
                )
                application, _ = TrainerApplication.objects.update_or_create(
                    user=profile_user,
                    defaults={
                        "specialty": spec["specialty"],
                        "career_years": spec["career_years"],
                        "career_description": f"{spec['specialty']} 지도 경력 {spec['career_years']}년",
                        "introduction": spec["introduction"],
                        "activity_url": "",
                        "status": TrainerApplication.Status.APPROVED,
                        "rejection_reason": "",
                        "reviewed_by": admin,
                        "submitted_at": now - timedelta(days=30),
                        "reviewed_at": now - timedelta(days=29),
                    },
                )
                profile, _ = TrainerProfile.objects.update_or_create(
                    user=profile_user,
                    defaults={
                        "specialty": spec["specialty"],
                        "career_years": spec["career_years"],
                        "introduction": spec["introduction"],
                        "activity_url": "",
                        "is_verified": True,
                        "verified_at": application.reviewed_at,
                    },
                )
                trainers[spec["key"]] = profile

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
                    "description": "헬스장 입문자가 주 3회 따라 할 수 있는 전신 근력 루틴입니다. 스쿼트, 힙힌지, 밀기와 당기기 동작을 단계별로 익힙니다.",
                    "seller": "strength",
                    "category": "bodybuilding",
                    "goals": ["strength", "muscle-gain"],
                    "difficulty": Product.Difficulty.BEGINNER,
                    "weeks": 8,
                    "sessions": 3,
                    "price": 19000,
                    "image": "strength.png",
                    "days_ago": 2,
                    "colors": ("#182433", "#7CE4B6"),
                    "rows": [(1, "스쿼트", 3, "10회", "가벼운 중량"), (1, "푸시업", 3, "8회", "무릎 대고 가능")],
                },
                {
                    "slug": "demo-upper-body",
                    "title": "상체 근육 집중 6주 프로그램",
                    "short_description": "등과 가슴, 어깨를 균형 있게 발달시키는 상체 분할 루틴",
                    "description": "기본 프레스와 로우 동작을 중심으로 상체 근육의 균형을 만드는 6주 프로그램입니다.",
                    "seller": "strength",
                    "category": "bodybuilding",
                    "goals": ["muscle-gain", "body-shape"],
                    "difficulty": Product.Difficulty.INTERMEDIATE,
                    "weeks": 6,
                    "sessions": 4,
                    "price": 24000,
                    "image": "strength.png",
                    "days_ago": 4,
                    "colors": ("#182433", "#7CE4B6"),
                    "rows": [(1, "벤치프레스", 4, "8회", "여유 반복 2회"), (1, "랫풀다운", 4, "10회", "견갑 하강")],
                },
                {
                    "slug": "demo-5k-running",
                    "title": "첫 5K 완주 러닝 플랜",
                    "short_description": "걷기와 달리기를 조합해 5K 완주를 준비하는 프로그램",
                    "description": "러닝 초보자를 위한 주 4회, 6주 단계별 훈련 계획입니다.",
                    "seller": "running",
                    "category": "running",
                    "goals": ["fitness", "stress-relief"],
                    "difficulty": Product.Difficulty.BEGINNER,
                    "weeks": 6,
                    "sessions": 4,
                    "price": 15000,
                    "image": "running.png",
                    "days_ago": 3,
                    "colors": ("#1D3557", "#F4A261"),
                    "rows": [(1, "걷기+조깅", 1, "30분", "대화 가능한 강도"), (2, "이지런", 1, "25분", "천천히 달리기")],
                },
                {
                    "slug": "demo-10k-pace",
                    "title": "10K 기록 단축 페이스 러닝",
                    "short_description": "이지런과 템포런을 조합한 중급자 8주 러닝 계획",
                    "description": "주간 거리와 강도를 점진적으로 높이며 10K 기록 단축을 준비하는 프로그램입니다.",
                    "seller": "running",
                    "category": "running",
                    "goals": ["fitness", "stress-relief"],
                    "difficulty": Product.Difficulty.INTERMEDIATE,
                    "weeks": 8,
                    "sessions": 4,
                    "price": 27000,
                    "image": "running.png",
                    "days_ago": 6,
                    "colors": ("#1D3557", "#F4A261"),
                    "rows": [(1, "이지런", 1, "40분", "편안한 호흡"), (1, "템포런", 1, "20분", "목표 페이스보다 천천히")],
                },
                {
                    "slug": "demo-home-mobility",
                    "title": "하루 20분 홈트와 모빌리티",
                    "short_description": "장비 없이 집에서 진행하는 근력·유연성 프로그램",
                    "description": "바쁜 일상에서도 실천할 수 있는 주 5회 홈트레이닝 루틴입니다.",
                    "seller": "balance",
                    "category": "home-training",
                    "goals": ["weight-loss", "body-shape"],
                    "difficulty": Product.Difficulty.INTERMEDIATE,
                    "weeks": 4,
                    "sessions": 5,
                    "price": 12000,
                    "image": "home-training.png",
                    "days_ago": 1,
                    "colors": ("#312244", "#C77DFF"),
                    "rows": [(1, "버드독", 3, "좌우 10회", "허리 중립"), (1, "런지", 3, "좌우 12회", "무릎 정렬")],
                },
                {
                    "slug": "demo-powerlifting-5x5",
                    "title": "5×5 파워리프팅 기초 루틴",
                    "short_description": "스쿼트·벤치프레스·데드리프트의 기본을 만드는 프로그램",
                    "description": "3대 운동의 자세와 점진적 과부하를 함께 관리하는 10주 파워리프팅 입문 루틴입니다.",
                    "seller": "strength",
                    "category": "powerlifting",
                    "goals": ["strength", "muscle-gain"],
                    "difficulty": Product.Difficulty.INTERMEDIATE,
                    "weeks": 10,
                    "sessions": 3,
                    "price": 39000,
                    "image": "powerlifting.png",
                    "days_ago": 5,
                    "colors": ("#25243A", "#8067DC"),
                    "rows": [(1, "백스쿼트", 5, "5회", "RPE 7"), (1, "벤치프레스", 5, "5회", "정지 동작")],
                },
                {
                    "slug": "demo-crossfit-conditioning",
                    "title": "6주 크로스핏 컨디셔닝",
                    "short_description": "케틀벨과 맨몸 동작으로 완성하는 전신 체력 프로그램",
                    "description": "동작 숙련도와 체력에 맞춰 강도를 조절할 수 있는 주 4회 기능성 운동 루틴입니다.",
                    "seller": "crossfit",
                    "category": "crossfit",
                    "goals": ["fitness", "weight-loss"],
                    "difficulty": Product.Difficulty.INTERMEDIATE,
                    "weeks": 6,
                    "sessions": 4,
                    "price": 29000,
                    "image": "crossfit.png",
                    "days_ago": 7,
                    "colors": ("#17363A", "#39B7B3"),
                    "rows": [(1, "케틀벨 스윙", 5, "15회", "허리 중립"), (1, "박스 스텝업", 4, "좌우 10회", "무릎 정렬")],
                },
                {
                    "slug": "demo-daily-stretching",
                    "title": "하루 10분 전신 스트레칭",
                    "short_description": "굳은 어깨와 고관절을 편안하게 풀어주는 데일리 루틴",
                    "description": "운동 전후 또는 업무 중에도 따라 할 수 있는 부위별 전신 스트레칭 프로그램입니다.",
                    "seller": "balance",
                    "category": "stretching",
                    "goals": ["body-shape", "stress-relief"],
                    "difficulty": Product.Difficulty.BEGINNER,
                    "weeks": 4,
                    "sessions": 6,
                    "price": 9000,
                    "image": "stretching.png",
                    "days_ago": 8,
                    "colors": ("#E9F4FF", "#4B76B8"),
                    "rows": [(1, "사이드 스트레칭", 2, "좌우 30초", "편안한 호흡"), (1, "고관절 스트레칭", 2, "좌우 40초", "통증 없는 범위")],
                },
                {
                    "slug": "demo-lower-body-glute",
                    "title": "하체와 힙 집중 6주 루틴",
                    "short_description": "스쿼트와 힙힌지를 중심으로 하체 기초를 만드는 프로그램",
                    "description": "둔근과 하체 근력을 균형 있게 강화하도록 구성한 주 3회 프로그램입니다.",
                    "seller": "strength",
                    "category": "bodybuilding",
                    "goals": ["muscle-gain", "body-shape"],
                    "difficulty": Product.Difficulty.BEGINNER,
                    "weeks": 6,
                    "sessions": 3,
                    "price": 21000,
                    "image": "strength.png",
                    "days_ago": 9,
                    "colors": ("#243B53", "#63B3ED"),
                    "rows": [(1, "고블릿 스쿼트", 3, "12회", "발바닥 전체 지지"), (1, "힙 브리지", 4, "15회", "정점 1초 유지")],
                },
                {
                    "slug": "demo-hypertrophy-split",
                    "title": "주 4일 근비대 분할 프로그램",
                    "short_description": "상·하체 분할로 운동량과 회복을 관리하는 중급 루틴",
                    "description": "부위별 훈련량과 회복일을 함께 설계한 8주 근비대 프로그램입니다.",
                    "seller": "strength",
                    "category": "bodybuilding",
                    "goals": ["muscle-gain", "strength"],
                    "difficulty": Product.Difficulty.INTERMEDIATE,
                    "weeks": 8,
                    "sessions": 4,
                    "price": 32000,
                    "image": "strength.png",
                    "days_ago": 10,
                    "colors": ("#1F2937", "#F59E0B"),
                    "rows": [(1, "인클라인 프레스", 4, "10회", "가슴 상부 집중"), (1, "바벨 로우", 4, "8회", "허리 중립")],
                },
                {
                    "slug": "demo-half-marathon",
                    "title": "첫 하프마라톤 12주 플랜",
                    "short_description": "기초 지구력부터 장거리 적응까지 이어지는 러닝 계획",
                    "description": "10K 완주 경험자를 대상으로 장거리 주행과 회복을 단계적으로 구성했습니다.",
                    "seller": "running",
                    "category": "running",
                    "goals": ["fitness", "stress-relief"],
                    "difficulty": Product.Difficulty.INTERMEDIATE,
                    "weeks": 12,
                    "sessions": 4,
                    "price": 35000,
                    "image": "running.png",
                    "days_ago": 11,
                    "colors": ("#0F4C5C", "#E36414"),
                    "rows": [(1, "이지런", 1, "45분", "편안한 호흡"), (1, "롱런", 1, "70분", "수분 섭취 연습")],
                },
                {
                    "slug": "demo-running-interval",
                    "title": "체지방 감소 인터벌 러닝",
                    "short_description": "빠른 달리기와 회복 구간을 조합한 5주 프로그램",
                    "description": "짧은 시간 안에 심폐 자극을 높이되 회복 구간을 충분히 확보한 러닝 루틴입니다.",
                    "seller": "running",
                    "category": "running",
                    "goals": ["weight-loss", "fitness"],
                    "difficulty": Product.Difficulty.INTERMEDIATE,
                    "weeks": 5,
                    "sessions": 3,
                    "price": 18000,
                    "image": "running.png",
                    "days_ago": 12,
                    "colors": ("#264653", "#E9C46A"),
                    "rows": [(1, "워밍업 조깅", 1, "10분", "호흡 준비"), (1, "인터벌", 6, "1분/2분", "빠르게/천천히")],
                },
                {
                    "slug": "demo-office-posture",
                    "title": "직장인 자세 회복 홈트",
                    "short_description": "굽은 어깨와 약해진 코어를 위한 하루 15분 루틴",
                    "description": "오래 앉아 있는 직장인의 상체 정렬과 코어 활성화를 돕는 프로그램입니다.",
                    "seller": "balance",
                    "category": "home-training",
                    "goals": ["body-shape", "stress-relief"],
                    "difficulty": Product.Difficulty.BEGINNER,
                    "weeks": 4,
                    "sessions": 5,
                    "price": 11000,
                    "image": "home-training.png",
                    "days_ago": 13,
                    "colors": ("#334155", "#38BDF8"),
                    "rows": [(1, "월 슬라이드", 3, "12회", "갈비뼈 들리지 않게"), (1, "데드버그", 3, "좌우 10회", "허리 바닥 유지")],
                },
                {
                    "slug": "demo-low-impact-home",
                    "title": "관절 부담을 낮춘 저강도 홈트",
                    "short_description": "점프 없이 전신을 움직이는 입문자용 운동 프로그램",
                    "description": "층간소음과 관절 부담을 줄이면서 기초 체력을 높일 수 있도록 구성했습니다.",
                    "seller": "balance",
                    "category": "home-training",
                    "goals": ["fitness", "weight-loss"],
                    "difficulty": Product.Difficulty.BEGINNER,
                    "weeks": 6,
                    "sessions": 4,
                    "price": 14000,
                    "image": "home-training.png",
                    "days_ago": 14,
                    "colors": ("#365314", "#BEF264"),
                    "rows": [(1, "체어 스쿼트", 3, "10회", "의자 높이 조절"), (1, "스탠딩 니업", 3, "좌우 12회", "천천히 수행")],
                },
                {
                    "slug": "demo-deadlift-technique",
                    "title": "데드리프트 자세 교정 4주",
                    "short_description": "힙힌지 패턴과 바벨 경로를 익히는 기술 집중 루틴",
                    "description": "중량보다 안정적인 자세를 우선하며 데드리프트의 기본 패턴을 반복 학습합니다.",
                    "seller": "strength",
                    "category": "powerlifting",
                    "goals": ["strength", "muscle-gain"],
                    "difficulty": Product.Difficulty.INTERMEDIATE,
                    "weeks": 4,
                    "sessions": 3,
                    "price": 22000,
                    "image": "powerlifting.png",
                    "days_ago": 15,
                    "colors": ("#292524", "#F97316"),
                    "rows": [(1, "루마니안 데드리프트", 4, "8회", "햄스트링 긴장"), (1, "포즈 데드리프트", 3, "5회", "무릎 아래 정지")],
                },
                {
                    "slug": "demo-squat-peak",
                    "title": "스쿼트 기록 향상 8주 사이클",
                    "short_description": "볼륨 훈련부터 최고 중량 도전까지 연결하는 프로그램",
                    "description": "스쿼트 수행 기록을 바탕으로 주차별 강도를 조절하는 중상급 프로그램입니다.",
                    "seller": "strength",
                    "category": "powerlifting",
                    "goals": ["strength"],
                    "difficulty": Product.Difficulty.ADVANCED,
                    "weeks": 8,
                    "sessions": 3,
                    "price": 42000,
                    "image": "powerlifting.png",
                    "days_ago": 16,
                    "colors": ("#18181B", "#A78BFA"),
                    "rows": [(1, "컴피티션 스쿼트", 5, "5회", "RPE 7"), (1, "템포 스쿼트", 3, "6회", "하강 3초")],
                },
                {
                    "slug": "demo-crossfit-foundation",
                    "title": "크로스핏 입문 동작 클래스",
                    "short_description": "기초 체조와 웨이트리프팅 패턴을 익히는 4주 과정",
                    "description": "처음 크로스핏을 시작하는 사용자가 주요 동작을 안전하게 익히도록 구성했습니다.",
                    "seller": "crossfit",
                    "category": "crossfit",
                    "goals": ["fitness", "strength"],
                    "difficulty": Product.Difficulty.BEGINNER,
                    "weeks": 4,
                    "sessions": 3,
                    "price": 17000,
                    "image": "crossfit.png",
                    "days_ago": 17,
                    "colors": ("#164E63", "#67E8F9"),
                    "rows": [(1, "에어 스쿼트", 4, "12회", "깊이보다 정렬"), (1, "링 로우", 4, "10회", "몸통 일직선")],
                },
                {
                    "slug": "demo-kettlebell-engine",
                    "title": "케틀벨 전신 체력 강화",
                    "short_description": "스윙과 캐리 동작으로 완성하는 30분 컨디셔닝",
                    "description": "한 개의 케틀벨로 근력과 심폐 체력을 함께 훈련하는 실전 프로그램입니다.",
                    "seller": "crossfit",
                    "category": "crossfit",
                    "goals": ["fitness", "weight-loss"],
                    "difficulty": Product.Difficulty.INTERMEDIATE,
                    "weeks": 6,
                    "sessions": 4,
                    "price": 25000,
                    "image": "crossfit.png",
                    "days_ago": 18,
                    "colors": ("#134E4A", "#5EEAD4"),
                    "rows": [(1, "케틀벨 스윙", 6, "15회", "엉덩이로 추진"), (1, "수트케이스 캐리", 4, "좌우 30m", "몸통 기울지 않게")],
                },
                {
                    "slug": "demo-morning-mobility",
                    "title": "아침을 여는 12분 모빌리티",
                    "short_description": "척추와 고관절을 부드럽게 깨우는 매일 아침 루틴",
                    "description": "잠든 몸을 무리 없이 깨우고 하루의 움직임을 준비하는 짧은 모빌리티 프로그램입니다.",
                    "seller": "balance",
                    "category": "stretching",
                    "goals": ["stress-relief", "body-shape"],
                    "difficulty": Product.Difficulty.BEGINNER,
                    "weeks": 4,
                    "sessions": 7,
                    "price": 8000,
                    "image": "stretching.png",
                    "days_ago": 19,
                    "colors": ("#E0F2FE", "#0284C7"),
                    "rows": [(1, "캣카우", 2, "10회", "척추 마디 움직이기"), (1, "90/90 회전", 2, "좌우 8회", "골반 천천히 전환")],
                },
                {
                    "slug": "demo-sleep-stretch",
                    "title": "숙면을 위한 저녁 스트레칭",
                    "short_description": "긴장을 낮추고 편안한 호흡을 돕는 취침 전 루틴",
                    "description": "목과 등, 골반 주변의 긴장을 천천히 풀어 하루를 마무리하는 프로그램입니다.",
                    "seller": "balance",
                    "category": "stretching",
                    "goals": ["stress-relief"],
                    "difficulty": Product.Difficulty.BEGINNER,
                    "weeks": 4,
                    "sessions": 7,
                    "price": 7000,
                    "image": "stretching.png",
                    "days_ago": 20,
                    "colors": ("#312E81", "#C4B5FD"),
                    "rows": [(1, "차일드 포즈", 2, "60초", "느린 복식호흡"), (1, "누운 척추 회전", 2, "좌우 45초", "어깨 바닥 유지")],
                },
            ]

            products = []
            for spec in product_specs:
                thumbnail_key = _save_if_missing(
                    f"demo/product-thumbnails-v2/{spec['slug']}.png",
                    _demo_thumbnail_bytes(
                        filename=spec["image"],
                        primary=spec["colors"][0],
                        accent=spec["colors"][1],
                    ),
                )
                exercise_names = ", ".join(row[1] for row in spec["rows"])
                detailed_description = (
                    f"{spec['description']}\n\n"
                    f"이 프로그램은 총 {spec['weeks']}주 동안 주 {spec['sessions']}회 진행하도록 설계했습니다. "
                    "처음부터 무리하게 강도를 높이지 않고, 매주 수행 기록을 확인하며 안정적으로 다음 단계로 넘어갑니다.\n\n"
                    f"주요 구성\n- 핵심 동작: {exercise_names}\n"
                    "- 운동 전 준비 동작과 운동 후 회복 가이드\n"
                    "- 반복 횟수, 세트 수, 강도 조절 기준\n"
                    "- 컨디션이 좋지 않은 날 사용할 수 있는 대체 동작\n\n"
                    "추천 대상\n운동 계획을 매번 새로 짜기 어렵거나, 정해진 순서에 따라 꾸준히 운동하고 싶은 분께 추천합니다. "
                    "각 동작은 통증이 없는 범위에서 진행하고 개인의 운동 경험과 회복 상태에 맞춰 강도를 조절해 주세요.\n\n"
                    "구매 후 제공되는 루틴 파일에는 주차별 운동 순서와 세트·반복 기준, 수행 메모가 정리되어 있습니다."
                )
                product, _ = Product.objects.update_or_create(
                    slug=spec["slug"],
                    defaults={
                        "seller": trainers[spec["seller"]],
                        "category": Category.objects.get(slug=spec["category"]),
                        "title": spec["title"],
                        "short_description": spec["short_description"],
                        "description": detailed_description,
                        "difficulty": spec["difficulty"],
                        "duration_weeks": spec["weeks"],
                        "sessions_per_week": spec["sessions"],
                        "price": spec["price"],
                        "thumbnail_object_key": thumbnail_key,
                        "status": Product.Status.DRAFT,
                        "published_at": now - timedelta(days=spec["days_ago"]),
                    },
                )
                product.goals.set(ExerciseGoal.objects.filter(slug__in=spec["goals"]))

                for detail_index, colors in enumerate(
                    (spec["colors"], (spec["colors"][1], spec["colors"][0]))
                ):
                    detail_key = _save_if_missing(
                        f"demo/product-detail-images-v1/{spec['slug']}-{detail_index + 1}.png",
                        _thumbnail_bytes(primary=colors[0], accent=colors[1]),
                    )
                    ProductDetailImage.objects.update_or_create(
                        product=product,
                        sort_order=detail_index,
                        defaults={
                            "object_key": detail_key,
                            "original_filename": f"{spec['slug']}-detail-{detail_index + 1}.png",
                        },
                    )

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

            reviewer_specs = [
                ("reviewer1@routine-market.local", "최현우", "꾸준한헬린이"),
                ("reviewer2@routine-market.local", "김서연", "오늘도러닝"),
                ("reviewer3@routine-market.local", "박준호", "건강한직장인"),
                ("reviewer4@routine-market.local", "이지수", "홈트생활"),
            ]
            reviewers = [
                _upsert_user(
                    email=email,
                    full_name=full_name,
                    nickname=nickname,
                    password=password,
                    role=User.Role.MEMBER,
                    is_staff=False,
                    is_superuser=False,
                )
                for email, full_name, nickname in reviewer_specs
            ]
            review_specs = [
                (0, 0, 5, "운동 순서와 중량 증가 기준이 명확해서 처음 헬스장을 다니는 데 큰 도움이 됐어요."),
                (0, 1, 4, "주 3회 일정이라 부담이 적고 기본 동작을 반복해서 익히기 좋았습니다."),
                (1, 2, 5, "상체 운동 구성이 균형 잡혀 있고 기록표가 있어 매주 변화를 확인하기 편합니다."),
                (1, 3, 4, "설명이 간결하고 운동 시간이 길지 않아 퇴근 후에도 꾸준히 진행하고 있어요."),
                (2, 0, 5, "걷기와 달리기 비율을 단계적으로 조절해 주어 처음으로 5K를 완주했습니다."),
                (2, 3, 5, "회차별 목표 페이스가 구체적이라 혼자 달릴 때도 계획을 지키기 쉬웠어요."),
                (3, 1, 5, "템포런과 회복주 배치가 좋아 무리하지 않고 기록을 단축할 수 있었습니다."),
                (3, 2, 4, "러닝 경험이 조금 있는 사람에게 적당한 난이도이고 주간 계획이 실용적입니다."),
                (4, 0, 4, "매트 하나만 있으면 되고 20분 안에 끝나서 아침 루틴으로 활용하기 좋습니다."),
                (4, 3, 5, "허리와 골반이 뻐근한 날 따라 하면 몸이 한결 편안해져서 자주 사용하고 있어요."),
                (5, 1, 5, "5×5 진행 방식과 휴식 기준이 잘 정리되어 있어 중량을 안정적으로 올렸습니다."),
                (5, 2, 5, "스쿼트와 벤치프레스 자세 체크 항목이 특히 유용하고 기록 관리도 편합니다."),
                (6, 0, 4, "동작별 대체 운동이 함께 있어 현재 체력에 맞춰 강도를 조절할 수 있었습니다."),
                (6, 3, 5, "짧은 시간에도 운동량이 충분하고 매주 구성이 달라 지루하지 않게 진행했어요."),
                (7, 1, 5, "목과 어깨가 자주 굳는 직장인에게 잘 맞고 설명대로 호흡하니 훨씬 편안합니다."),
                (7, 2, 4, "10분 정도라 매일 실천하기 좋고 운동 전 워밍업으로도 유용하게 사용 중입니다."),
            ]
            for sequence, (product_index, reviewer_index, rating, content) in enumerate(
                review_specs, start=1
            ):
                review_product = products[product_index]
                reviewer = reviewers[reviewer_index]
                order_item = OrderItem.objects.filter(
                    order__buyer=reviewer,
                    order__status=Order.Status.PAID,
                    product=review_product,
                ).first()
                if order_item is None:
                    product_file = review_product.files.get(is_current=True)
                    paid_at = now - timedelta(days=sequence + 2)
                    order = Order.objects.create(
                        buyer=reviewer,
                        status=Order.Status.PAID,
                        total_amount=review_product.price,
                        paid_at=paid_at,
                    )
                    order_item = OrderItem.objects.create(
                        order=order,
                        product=review_product,
                        product_file=product_file,
                        seller=review_product.seller,
                        product_title=review_product.title,
                        seller_name=review_product.seller.user.nickname,
                        unit_price=review_product.price,
                    )
                Review.objects.update_or_create(
                    author=reviewer,
                    product=review_product,
                    defaults={
                        "order_item": order_item,
                        "rating": rating,
                        "content": content,
                        "is_visible": True,
                    },
                )

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
            CartItem.objects.get_or_create(cart=cart, product=products[2])
            WishlistItem.objects.get_or_create(user=buyer, product=products[4])

        self.stdout.write(self.style.SUCCESS("Routine Market 데모 데이터를 구성했습니다."))
        if options["reset"]:
            self.stdout.write("데모 구매 흐름을 초기 상태로 복구했습니다.")
        self.stdout.write(f"공통 데모 비밀번호: {password}")
        self.stdout.write("관리자: admin@routine-market.local")
        self.stdout.write("구매자: buyer@routine-market.local")
        self.stdout.write("트레이너: trainer@routine-market.local")
        self.stdout.write("승인 대기: pending@routine-market.local")
