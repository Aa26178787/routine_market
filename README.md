# Routine Market

검증된 트레이너가 XLSX 운동 루틴을 판매하고, 사용자가 검색·토스페이먼츠 결제·다운로드·리뷰까지 경험할 수 있는 Django 기반 디지털 마켓플레이스입니다.

## 주요 기능

- 이메일 인증 회원가입, 로그인·로그아웃, 새 주소 인증 기반 이메일 변경과 이름·닉네임 수정
- 로그인 세션을 유지하는 비밀번호 변경과 이메일 기반 비밀번호 재설정
- 반복 로그인 실패 제한과 비밀번호 확인 기반 계정 비활성화
- 트레이너 인증 신청, 복수 자격 증빙 제출, 관리자 승인·거절
- 인증 트레이너 공개 프로필 조회 및 본인 전문 분야·경력·소개·활동 URL 수정
- 상품 등록·수정·판매 중지, XLSX 검증과 구매 당시 파일 버전 보존
- 검색·필터·정렬·찜·장바구니·토스페이먼츠 결제·구매 내역
- 구매자 전용 파일 다운로드, 다운로드 이력, 구매 인증 리뷰
- 판매자 통계와 Django Admin 운영 화면

## 기술 구성

- Python 3.14, Django 5.2 LTS, Django Template
- SQLite(기본 개발 환경) 또는 PostgreSQL 16
- 비공개 AWS S3 미디어 저장소, EC2·Gunicorn·Nginx, RDS PostgreSQL
- Pillow, django-storages, boto3, psycopg

## 로컬 실행

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

기본 주소는 `http://127.0.0.1:8000/`, 상태 확인 주소는 `/health/`입니다. `.env`는 Git에 포함되지 않습니다. 기본값은 SQLite와 로컬 미디어 저장소이며, 상세 설정값은 주석이 포함된 `.env.example`을 기준으로 합니다.

## 데모 데이터

`seed_demo`는 관리자·구매자·트레이너·승인 대기 신청과 상품·주문·리뷰를 구성합니다. `--reset`은 데모 데이터를 동일한 초기 상태로 복원하며 `DEBUG=true`에서만 실행됩니다.

```powershell
python manage.py seed_demo --reset
```

기본 공통 비밀번호는 `RoutineDemo123!`이며 `DEMO_PASSWORD` 환경변수로 변경할 수 있습니다. 실제 운영 환경에서는 별도 비밀번호를 사용해야 합니다.

## PostgreSQL과 S3

PostgreSQL은 `.env`에서 `DB_ENGINE=postgresql`로 전환합니다. DB 비밀번호는 로컬 `pgpass.conf` 또는 배포 환경의 비밀 저장소 사용을 권장합니다.

S3는 `USE_S3=true`, 버킷명과 리전을 지정해 활성화합니다. 장기 AWS 키를 `.env`에 저장하지 말고 로컬 AWS 프로필 또는 EC2 IAM 역할을 사용합니다. 구매 파일은 권한 확인 후 기본 300초짜리 서명 URL로 전달됩니다. 자세한 내용은 [AWS 연동 가이드](docs/aws-setup.md)와 [배포 구성](deploy/README.md)을 참고하세요.

## 이메일

개발 환경은 인증·재설정 메일을 터미널에 출력합니다. 운영에서는 SMTP 백엔드와 발신 주소를 설정하고, 회원가입·이메일 변경 인증 및 비밀번호 재설정 메일을 실제 수신 환경에서 검증해야 합니다.

## 토스페이먼츠

토스페이먼츠 개발자센터에서 발급한 주문서형·결제창형 테스트 클라이언트 키(`test_gck_`)와 시크릿 키(`test_gsk_`)를 각각 `TOSS_PAYMENTS_CLIENT_KEY`, `TOSS_PAYMENTS_SECRET_KEY`에 설정합니다. 시크릿 키는 브라우저나 저장소에 노출하지 않습니다. 결제 성공 리다이렉트의 주문번호와 금액을 서버 주문 데이터와 대조한 뒤 승인 API를 호출하며, 승인된 `paymentKey`와 결제수단 및 영수증 URL을 주문에 저장합니다.

## 검증

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test
```

## 문서

- [요구사항 명세서](docs/requirements-specification.md)
- [요구사항 구현 추적표](docs/requirements-traceability.md)
- [ERD](docs/erd.md)
- [개발 현황 및 남은 작업](docs/project-status.md)
- [UI 디자인 시스템](docs/ui-design-system.md)
- [MVP 시연 시나리오](docs/demo-scenario.md)
- [AWS 연동 가이드](docs/aws-setup.md)
- [AWS 운영 배포 구성](deploy/README.md)
- [서비스 이용약관 초안](docs/terms-draft.md)
- [개인정보 처리방침 초안](docs/privacy-policy-draft.md)
- [운동 프로그램 면책 고지 초안](docs/exercise-disclaimer-draft.md)

법적 문서 3종은 검토 전 초안이며 실제 서비스 공개 전에 사업 정보, 처리위탁·보유기간·연락처를 확정하고 전문가 검토를 받아야 합니다.
