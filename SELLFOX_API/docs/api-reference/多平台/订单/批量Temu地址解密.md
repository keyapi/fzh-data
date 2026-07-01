# 批量Temu地址解密

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/multiplatform/order/decryptAddress.json:
    post:
      summary: 批量Temu地址解密
      deprecated: false
      description: ''
      operationId: decryptAddressUsingPOST
      tags:
        - 多平台/订单
        - 多平台/多平台订单
      parameters:
        - name: access_token
          in: query
          description: 通过获取token接口获得的token，详见 [获取 Access Token](doc-1589130)
          required: true
          example: '{{access_token}}'
          schema:
            type: string
        - name: client_id
          in: query
          description: client_id, 获取方式详见 [申请API权限](1748360)
          required: true
          example: '{{client_id}}'
          schema:
            type: string
        - name: timestamp
          in: query
          description: 13位毫秒时间戳，与当前时间差异不超过正负15分钟，示例：1668153260508
          required: true
          example: '121212'
          schema:
            type: string
        - name: nonce
          in: query
          description: '随机整数值，保证每个请求唯一，示例：11251 '
          required: true
          example: '121212'
          schema:
            type: string
        - name: sign
          in: query
          description: 请求签名，详见  [生成sign（签名）](doc-1749562)
          required: true
          example: '121212121'
          schema:
            type: string
        - name: Content-Type
          in: header
          description: 固定再header位置加入Content-Type:application/json
          example: application/json
          schema:
            type: string
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/TemuDecryptAddressOpenQO'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABTemuDecryptAddressOpenVO%C2%BB
          headers: {}
          x-apifox-name: ''
        '201':
          description: Created
          headers: {}
          x-apifox-name: ''
        '401':
          description: Unauthorized
          headers: {}
          x-apifox-name: ''
        '403':
          description: Forbidden
          headers: {}
          x-apifox-name: ''
        '404':
          description: Not Found
          headers: {}
          x-apifox-name: ''
      security: []
      x-order: '2147483647'
      x-apifox-folder: 多平台/订单
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-422323119-run
components:
  schemas:
    TemuDecryptAddressOpenQO:
      type: object
      properties:
        packageSns:
          type: array
          description: 包裹号集合
          items:
            type: string
      title: TemuDecryptAddressOpenQO
      x-apifox-orders:
        - packageSns
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«TemuDecryptAddressOpenVO»:
      type: object
      properties:
        requestId:
          type: string
        code:
          type: integer
          format: int32
          description: code(默认0代表成功)
        msg:
          type: string
          description: 错误信息
        data:
          $ref: '#/components/schemas/TemuDecryptAddressOpenVO'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«TemuDecryptAddressOpenVO»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    TemuDecryptAddressOpenVO:
      type: object
      required:
        - successNum
        - failNum
        - successData
        - failData
      properties:
        successNum:
          type: integer
          format: int32
          description: 解密成功数量
        failNum:
          type: integer
          format: int32
          description: 解密失败数量
        successData:
          type: array
          description: 解密成功包裹号
          items:
            type: string
        failData:
          type: array
          description: 解密失败数据
          items:
            $ref: '#/components/schemas/FailDTO'
      title: TemuDecryptAddressOpenVO
      x-apifox-orders:
        - successNum
        - failNum
        - successData
        - failData
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FailDTO:
      type: object
      required:
        - packageSn
        - errorMsg
      properties:
        packageSn:
          type: string
          description: 包裹号
        errorMsg:
          type: string
          description: 错误信息
      title: FailDTO
      x-apifox-orders:
        - packageSn
        - errorMsg
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
