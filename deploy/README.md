# Routine Market AWS 배포 구성

## 대상 구조

- 서울 리전의 Ubuntu 24.04 EC2에서 Nginx와 Gunicorn 실행
- 동일 VPC의 비공개 Single-AZ RDS PostgreSQL 사용
- 기존 비공개 S3 버킷에 미디어 파일 저장
- EC2 인스턴스 역할로 S3에 접근하고 장기 AWS 키는 저장하지 않음
- DB 비밀번호는 RDS가 생성한 Secrets Manager 비밀로 관리

## 현재 배포

- 서비스 주소: `http://3.35.122.226/`
- 상태 확인: `http://3.35.122.226/health/`
- EC2: `i-09918a6f0f845e8de` (`t3.micro`, Ubuntu 24.04)
- RDS: `routine-market-db` (PostgreSQL 16.13, `db.t4g.micro`, Single-AZ)
- S3: `routine-market-108327566686-ap-northeast-2`
- 운영 리전: `ap-northeast-2`

현재 주소는 HTTP이다. 로그인과 구매 흐름 검증은 완료했지만 실제 공개 운영 전에는
도메인과 HTTPS를 적용해야 한다.

운영 데모 계정은 저장소에 기재된 개발용 기본 비밀번호를 사용하지 않는다.
배포 전용 비밀번호는 Secrets Manager의
`routine-market/production/demo-login`에서 관리한다.

## 서버 경로

- 애플리케이션: `/srv/routine-market`
- 운영 환경변수: `/etc/routine-market.env` (`root:root`, 권한 `600`)
- systemd 서비스: `/etc/systemd/system/routine-market.service`
- Nginx 설정: `/etc/nginx/sites-available/routine-market`

초기에는 EC2 공인 주소로 HTTP 검증을 진행한다. 도메인이 정해지기 전에는
`DJANGO_SECURE_SSL_REDIRECT=false`, `DJANGO_SECURE_HSTS_SECONDS=0`,
`DJANGO_SESSION_COOKIE_SECURE=false`, `DJANGO_CSRF_COOKIE_SECURE=false`를 사용한다.
도메인 연결 후 HTTPS를 적용하면서 네 값을 운영 보안값으로 변경한다.

EC2 역할의 S3 접근은 `s3-bucket-policy.json`으로 버킷의 `media/`
경로에만 허용한다. RDS 관리 비밀에는 EC2 역할을 대상으로
`secretsmanager:GetSecretValue` 리소스 정책을 설정한다.

## 배포 후 확인

```bash
sudo systemctl status routine-market nginx
curl -fsS http://127.0.0.1/health/
sudo journalctl -u routine-market -n 100 --no-pager
```

운영 데이터가 없는 최초 배포에서는 관리자 계정을 별도로 만들거나,
발표용 환경에 한해 잠시 `DEBUG=true`로 `seed_demo --reset`을 실행한 뒤 즉시
`DEBUG=false`로 복구한다.
