# Temu全托利润报表-查询结算明细-非商责平台售后补贴

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/financial/cross/temuAllReport/querySalesRelease.json:
    post:
      summary: Temu全托利润报表-查询结算明细-非商责平台售后补贴
      deprecated: false
      description: ''
      operationId: querySalesReleaseUsingPOST
      tags:
        - 多平台/财务
        - Temu全托利润报表
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
              $ref: '#/components/schemas/FinAggTemuAllSettlementDetailOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABFinAggSettlementSalesReleaseTemuAllOpenVO%C2%BB
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
      x-apifox-folder: 多平台/财务
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-426460066-run
components:
  schemas:
    FinAggTemuAllSettlementDetailOpenQo:
      type: object
      required:
        - startDate
        - endDate
      properties:
        currency:
          type: string
          description: 币种，原币种传空字符串
          enum:
            - CNY
            - USD
        shopIds:
          type: array
          description: 店铺ID
          items:
            type: integer
            format: int32
          examples:
            - - 1
              - 2
              - 3
        startDate:
          type: string
          description: 开始时间，格式：yyyy-MM-dd
          examples:
            - '2026-01-01'
        endDate:
          type: string
          description: 结束时间，格式：yyyy-MM-dd
          examples:
            - '2026-01-01'
        orderBy:
          type: string
          description: 排序字段, account_time=结算时间,amount=金额
          enum:
            - account_time
            - amount
          examples:
            - account_time
        desc:
          type: boolean
          description: 排序方式,true=desc(降序), false=asc(升序), 默认降序
          examples:
            - true
        pageNo:
          type: string
          description: 第几页,默认1
          examples:
            - 1
        pageSize:
          type: string
          description: 每页条数,默认20,最大200
          examples:
            - 20
      title: FinAggTemuAllSettlementDetailOpenQo
      x-apifox-orders:
        - currency
        - shopIds
        - startDate
        - endDate
        - orderBy
        - desc
        - pageNo
        - pageSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«FinAggSettlementSalesReleaseTemuAllOpenVO»:
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
          $ref: '#/components/schemas/FinAggSettlementSalesReleaseTemuAllOpenVO'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«FinAggSettlementSalesReleaseTemuAllOpenVO»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FinAggSettlementSalesReleaseTemuAllOpenVO:
      type: object
      properties:
        rows:
          type: array
          items:
            $ref: '#/components/schemas/FinAggSettlementSalesReleaseTemuAllPageOpenVO'
        totalPage:
          type: integer
          format: int32
          description: 总页数
        totalSize:
          type: integer
          format: int32
          description: 数据总条数
      title: FinAggSettlementSalesReleaseTemuAllOpenVO
      x-apifox-orders:
        - rows
        - totalPage
        - totalSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FinAggSettlementSalesReleaseTemuAllPageOpenVO:
      type: object
      properties:
        currency:
          type: string
          description: 币种
        shopId:
          type: string
          description: 店铺Id
        shopName:
          type: string
          description: 店铺名称
        accountType:
          type: string
          description: 账务类型(只有【结算】)
        feeName:
          type: string
          description: 费用名称(只有【非商责平台售后补贴】)
        afterSaleSn:
          type: string
          description: 售后单号
        parentOrderSn:
          type: string
          description: 订单编号
        subPurchaseOrderSn:
          type: string
          description: 备货单号
        msku:
          type: string
          description: 产品ID
        mskuCode:
          type: string
          description: MSKU
        mskuAttribute:
          type: string
          description: MSKU属性
        amount:
          type: number
          description: 金额
        accountTime:
          type: string
          description: 结算时间
      title: FinAggSettlementSalesReleaseTemuAllPageOpenVO
      x-apifox-orders:
        - currency
        - shopId
        - shopName
        - accountType
        - feeName
        - afterSaleSn
        - parentOrderSn
        - subPurchaseOrderSn
        - msku
        - mskuCode
        - mskuAttribute
        - amount
        - accountTime
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
