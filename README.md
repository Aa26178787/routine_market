# Routine Market

운동 루틴 디지털 상품을 검색하고 가상 구매할 수 있는 Django 기반 마켓플레이스입니다.

## 로컬 실행

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

프로젝트 루트의 `.env.example`을 `.env`로 복사해 로컬 설정을 관리할 수 있습니다. `.env`는 Git에서 제외됩니다. 별도의 데이터베이스 설정이 없으면 개발용 SQLite를 사용합니다. PostgreSQL을 사용하려면 `DB_ENGINE=postgresql`을 지정하고 비밀번호는 로컬 `pgpass.conf` 또는 배포 환경의 비밀 저장소에서 제공합니다.

AWS S3 파일 저장소를 연결하려면 [AWS 연동 가이드](docs/aws-setup.md)를 참고하세요.

## 문서

- [요구사항 명세서](docs/requirements-specification.md)
- [ERD](docs/erd.md)
- [개발 현황 및 향후 작업](docs/project-status.md)
- [AWS 연동 가이드](docs/aws-setup.md)
