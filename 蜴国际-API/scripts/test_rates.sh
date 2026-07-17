#!/bin/bash
# 蜴国际 API 费用试算测试脚本
# 使用说明: 直接运行即可，脚本会自动获取 token 并调用费用试算
# 前置条件: curl 可用

BASE_URL="http://47.106.72.196"
TOKEN="$LIZARD_TOKEN"
KEY="$LIZARD_KEY"

# 检测可用的 Python（python3 在某些环境下是无效 stub）
PYTHON=""
for cmd in python python3; do
  if command -v "$cmd" >/dev/null 2>&1 && echo "print(1)" | "$cmd" 2>/dev/null; then
    PYTHON="$cmd"
    break
  fi
done
if [ -z "$PYTHON" ] && [ -f "/d/Python/Python3.10/python" ]; then
  PYTHON="/d/Python/Python3.10/python"
fi
if [ -z "$PYTHON" ]; then
  echo "Error: python not found"
  exit 1
fi

echo "========================================="
echo "蜴国际 API 费用试算测试"
echo "========================================="

# 1. 获取 access_token
echo ""
echo "[Step 1/2] 获取 access_token..."
echo "-----------------------------------------"
TOKEN_RESP=$(curl -s -X POST "${BASE_URL}/api/svc/getToken" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "app_token=${TOKEN}&app_key=${KEY}")

ACCESS_TOKEN=$(echo "$TOKEN_RESP" | $PYTHON -c "import sys,json; print(json.load(sys.stdin)['result']['access_token'])" 2>/dev/null)

if [ -z "$ACCESS_TOKEN" ]; then
  echo "Fail to parse access_token"
  echo "Response: $TOKEN_RESP"
  exit 1
fi

echo "access_token obtained"
CUST_CODE=$(echo "$TOKEN_RESP" | $PYTHON -c "import sys,json; print(json.load(sys.stdin)['result']['user_info']['u_customer_code'])" 2>/dev/null)
echo "customer_code: $CUST_CODE"

# 2. 费用试算 - ratesv2
echo ""
echo "[Step 2/2] 调用费用试算 (ratesv2)..."
echo "-----------------------------------------"

RATES_RESP=$(curl -s -X POST "${BASE_URL}/api/svc/ratesv2" \
  -H "Content-Type: application/json" \
  -H "Authorization: ${ACCESS_TOKEN}" \
  -d '{
    "reference_no": "test-'$(date +%s)'",
    "weight_unit_type": "1",
    "ca_zone": 0,
    "parcel_declared_value": 100,
    "parcel_quantity": 1,
    "box_list": [{
      "box_actual_weight": 10,
      "box_length": 12,
      "box_width": 10,
      "box_height": 8
    }],
    "oa_firstname": "Test Receiver",
    "oa_company": "Test Company",
    "oa_country": "US",
    "oa_state": "CA",
    "oa_city": "Los Angeles",
    "oa_postcode": "90001",
    "oa_street_address1": "100 Main Street",
    "oa_street_address2": "",
    "oa_telphone": "1234567890",
    "oa_doorplate": "",
    "oa_phone_ext": "",
    "signature_service": "",
    "shipper_address": {
      "shipper_name": "Dan-zhao",
      "shipper_postal_code": "77099",
      "shipper_address1": "10812 Fallstone Rd",
      "shipper_address2": "Suite 402",
      "shipper_state_province": "TX",
      "shipper_city": "Houston",
      "shipper_country": "US",
      "shipper_telphone": "2816770938"
    }
  }')

CODE=$(echo "$RATES_RESP" | $PYTHON -c "import sys,json; print(json.load(sys.stdin)['code'])" 2>/dev/null)

if [ "$CODE" = "200" ]; then
  echo "费用试算成功!"
  echo ""
  echo "$RATES_RESP" | PYTHONIOENCODING=utf-8 $PYTHON -c "
import sys, json
data = json.load(sys.stdin)
results = data['result']
print('--------------------------------------------------')
for sm_code, info in results.items():
    if 'err_msg' in info and info['err_msg']:
        print(f'  X {sm_code}: {info[\"err_msg\"]}')
    else:
        print(f'  OK {sm_code}')
        print(f'     总费用: \${info[\"total_charge\"]} {info[\"currency_code\"]}')
        print(f'     运输费: \${info[\"shipping_charge\"]}')
        if info.get('charge_detail'):
            for d in info['charge_detail']:
                print(f'       - {d[\"charge_desc\"]}: \${d[\"amount\"]}')
        print()
print('--------------------------------------------------')
"
else
  echo "费用试算失败 (code: $CODE)"
  echo "Response: $RATES_RESP"
fi

echo ""
echo "Done"
