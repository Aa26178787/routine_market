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

별도의 데이터베이스 설정이 없으면 개발용 SQLite를 사용합니다. PostgreSQL을 사용하려면 `.env.example`의 항목을 환경변수로 설정하고 `DB_ENGINE=postgresql`을 지정합니다.

## 문서

- [요구사항 명세서](docs/requirements-specification.md)
- [ERD](docs/erd.md)
- [개발 현황 및 향후 작업](docs/project-status.md)
