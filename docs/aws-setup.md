# Routine Market AWS 연동 가이드

## 1. 이번 연동 범위

1차 연동 대상은 상품 썸네일, 운동 루틴 파일, 트레이너 증빙 파일을 저장하는 Amazon S3입니다.

- 모든 파일은 하나의 비공개 버킷에 저장합니다.
- Django 서버는 AWS SDK의 기본 자격 증명 체인을 사용합니다.
- 구매 권한은 기존 Django 로직이 검사합니다.
- 권한 검사를 통과한 다운로드는 기본 300초 동안 유효한 S3 서명 URL로 전달합니다.
- 썸네일도 비공개 객체로 유지하고 화면을 표시할 때 서명 URL을 생성합니다.

RDS와 EC2는 S3 연결을 검증한 다음 단계에서 구성합니다. RDS는 과금과 네트워크 구성이 필요하고, EC2에는 장기 액세스 키 대신 IAM 역할을 연결합니다.

## 2. 권장 리전과 버킷

- 리전: `ap-northeast-2` (서울)
- 버킷 이름 예시: `routine-market-<AWS 계정 ID>-ap-northeast-2`
- S3 퍼블릭 액세스 차단: 모든 항목 활성화
- 객체 소유권: Bucket owner enforced
- 버전 관리: 초기에는 선택 사항, 운영 전 활성화 권장

버킷 이름은 전 세계에서 고유해야 하므로 AWS 계정 ID 등을 포함합니다.

## 3. 최소 IAM 권한

아래 정책의 두 버킷 ARN을 실제 버킷 이름으로 바꿉니다. 로컬 개발용 IAM 사용자 또는 역할에는 이 범위만 허용합니다.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::routine-market-<AWS 계정 ID>-ap-northeast-2"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::routine-market-<AWS 계정 ID>-ap-northeast-2/media/*"
    }
  ]
}
```

애플리케이션이 현재 파일을 직접 삭제하지 않는다면 `s3:DeleteObject`는 제외할 수 있습니다.

## 4. 로컬 인증

AWS CLI를 설치하고 브라우저 기반 IAM Identity Center 로그인을 사용하는 방법을 권장합니다.

```powershell
aws configure sso
aws sso login --profile routine-market
$env:AWS_PROFILE = "routine-market"
aws sts get-caller-identity
```

액세스 키와 시크릿 키는 저장소, `.env`, Django 설정에 기록하지 않습니다. EC2 배포 환경에서는 인스턴스 프로필(IAM 역할)을 사용하므로 별도 키 환경변수가 필요하지 않습니다.

## 5. Django 환경변수

PowerShell 세션에서 다음 값을 설정합니다.

```powershell
$env:AWS_PROFILE = "routine-market"
$env:USE_S3 = "true"
$env:AWS_STORAGE_BUCKET_NAME = "routine-market-<AWS 계정 ID>-ap-northeast-2"
$env:AWS_S3_REGION_NAME = "ap-northeast-2"
$env:AWS_MEDIA_LOCATION = "media"
$env:DOWNLOAD_URL_EXPIRES = "300"
```

`PRIVATE_FILE_DELIVERY`를 생략하면 S3 사용 시 `redirect`가 자동 선택됩니다. 로컬 파일 저장소에서는 `proxy`가 기본값입니다. AWS S3는 선택한 리전의 엔드포인트를 자동 사용하며, `AWS_S3_ENDPOINT_URL`은 LocalStack 같은 S3 호환 저장소에서만 별도로 지정합니다.

## 6. 연결 확인

환경변수와 AWS 로그인이 적용된 동일한 PowerShell 세션에서 실행합니다.

```powershell
python manage.py check
python manage.py shell -c "from django.core.files.base import ContentFile; from django.core.files.storage import default_storage; key=default_storage.save('healthcheck/s3.txt', ContentFile(b'ok')); print(key, default_storage.exists(key)); default_storage.delete(key)"
```

출력에 `True`가 표시되고 버킷에서 테스트 객체가 삭제되면 저장·조회·삭제 권한이 정상입니다.

현재 개발 계정에서는 서울 리전의 비공개 버킷 생성과 실제 저장·조회·서명 URL 생성·삭제 검증까지 완료했다. 로컬에서 다시 실행할 때는 먼저 `aws sso login --profile routine-market`으로 SSO 세션을 갱신한다.

## 7. 다음 AWS 단계

1. RDS PostgreSQL 생성 및 보안 그룹 연결
2. Secrets Manager 또는 EC2 환경 설정으로 DB 접속 정보 주입
3. EC2에 애플리케이션용 IAM 역할 연결
4. Gunicorn, Nginx, HTTPS 구성
5. 정적 파일 배포와 로그·백업·모니터링 구성
