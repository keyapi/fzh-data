# Walmart-创建WFS货件草稿

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /openapi/psi/walmart/wfsShipment/createDraft.json:
    post:
      summary: Walmart-创建WFS货件草稿
      deprecated: false
      description: ''
      operationId: createDraftUsingPOST
      tags:
        - 多平台/平台仓
        - WFS货件
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
              $ref: '#/components/schemas/WfsShipmentCreateDraftOpenQO'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABWfsShipmentResultVO%C2%ABstring%C2%BB%C2%BB
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
      x-apifox-folder: 多平台/平台仓
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-510029212-run
components:
  schemas:
    WfsShipmentCreateDraftOpenQO:
      type: object
      required:
        - shopId
        - expectedDeliveryDate
        - returnCity
        - returnPersonName
        - returnState
        - returnCountryCode
        - returnPostalCode
        - firstReturnAddress
        - itemList
      properties:
        shopId:
          type: string
          description: 店铺ID
        shopName:
          type: string
          description: 店铺名称，传入时需与shopId匹配
        expectedDeliveryDate:
          type: string
          description: 预计到货日期，yyyy-MM-dd
          examples:
            - '2026-01-01'
        returnCity:
          type: string
          description: 退货城市
        returnPersonName:
          type: string
          description: 退货收件人
        returnState:
          type: string
          description: 退货州/省
        returnCountryCode:
          type: string
          description: 退货国家码
        returnPostalCode:
          type: string
          description: 退货邮编
        firstReturnAddress:
          type: string
          description: 退货街道地址1
        secondReturnAddress:
          type: string
          description: 退货街道地址2
        itemList:
          type: array
          description: 产品信息
          items:
            $ref: '#/components/schemas/Item'
      title: WfsShipmentCreateDraftOpenQO
      x-apifox-orders:
        - shopId
        - shopName
        - expectedDeliveryDate
        - returnCity
        - returnPersonName
        - returnState
        - returnCountryCode
        - returnPostalCode
        - firstReturnAddress
        - secondReturnAddress
        - itemList
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    Item:
      type: object
      required:
        - productId
        - shipmentQty
        - packingType
        - boxQty
        - itemDesc
      properties:
        productId:
          type: string
          description: 产品ID，来源于wfsShipment/addableProductPageList返回的productId
        shipmentQty:
          type: integer
          format: int32
          description: 申报量
        packingType:
          type: integer
          format: int32
          description: 装箱类型：1-casePack，2-individual
        boxQty:
          type: integer
          format: int32
          description: 每箱数量
        itemDesc:
          type: string
          description: 产品描述
      title: Item
      x-apifox-orders:
        - productId
        - shipmentQty
        - packingType
        - boxQty
        - itemDesc
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«WfsShipmentResultVO«string»»:
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
          $ref: '#/components/schemas/WfsShipmentResultVO%C2%ABstring%C2%BB'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«WfsShipmentResultVO«string»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    WfsShipmentResultVO«string»:
      type: object
      title: WfsShipmentResultVO«string»
      x-apifox-orders: []
      properties: {}
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
