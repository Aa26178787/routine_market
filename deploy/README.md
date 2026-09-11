# Routine Market AWS 배포 구성

## 대상 구조

- 서울 리전의 Ubuntu 24.04 EC2에서 Nginx와 Gunicorn 실행
- 동일 VPC의 비공개 Single-AZ RDS PostgreSQL 사용
- 기존 비공개 S3 버킷에 미디어 파일 저장
- EC2 인스턴스 역할로 S3에 접근하고 장기 AWS 키는 저장하지 않음
- DB 비밀번호는 SSM Parameter Store의 SecureString으로 전달

## 서버 경로

- 애플리케이션: `/srv/routine-market`
- 운영 환경변수: `/etc/routine-market.env` (`root:root`, 권한 `600`)
- systemd 서비스: `/etc/systemd/system/routine-market.service`
- Nginx 설정: `/etc/nginx/sites-available/routine-market`

초기에는 EC2 공인 주소로 HTTP 검증을 진행한다. 도메인이 정해지기 전에는
`DJANGO_SECURE_SSL_REDIRECT=false`와 `DJANGO_SECURE_HSTS_SECONDS=0`을 사용한다.
도메인 연결 후 HTTPS를 적용하면서 두 값을 운영 보안값으로 변경한다.

## 배포 후 확인

```bash
sudo systemctl status routine-market nginx
curl -fsS http://127.0.0.1/health/
sudo journalctl -u routine-market -n 100 --no-pager
```

운영 데이터가 없는 최초 배포에서는 관리자 계정을 별도로 만들거나,
발표용 환경에 한해 잠시 `DEBUG=true`로 `seed_demo --reset`을 실행한 뒤 즉시
`DEBUG=false`로 복구한다.
