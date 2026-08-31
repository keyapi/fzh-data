# 多平台利润报表-查询结算明细-Shopify

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/financial/aggReport/settlement/shopifyPage.json:
    post:
      summary: 多平台利润报表-查询结算明细-Shopify
      deprecated: false
      description: ''
      operationId: settlementShopifyPageUsingPOST
      tags:
        - 多平台/财务
        - 多平台利润报表
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
              $ref: '#/components/schemas/FinAggShopifySettlementOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABFinAggSettlementShopifyOpenVO%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-426459620-run
components:
  schemas:
    FinAggShopifySettlementOpenQo:
      type: object
      required:
        - dayType
        - startDay
        - endDay
      properties:
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
        dayType:
          type: integer
          format: int32
          description: 时间类型，0=结算时间，1=支付时间，2=发货时间，3=订购时间
          enum:
            - 0
            - 1
            - 2
            - 3
          examples:
            - 0
        startDay:
          type: string
          description: 开始时间，格式：yyyy-MM-dd
          examples:
            - '2026-01-01'
        endDay:
          type: string
          description: 结束时间，格式：yyyy-MM-dd
          examples:
            - '2026-01-01'
        currency:
          type: string
          description: 币种，原币种传空字符串
          enum:
            - CNY
            - USD
            - CAD
            - MXN
            - BRL
            - COP
            - EUR
            - GBP
            - PLN
            - SEK
            - IDR
            - SGD
            - MYR
            - THB
            - VND
            - PHP
            - SAR
            - AED
            - TRY
            - JPY
            - AUD
        orderTypes:
          type: array
          description: 交易类型, order:付款 refund:退款
          items:
            type: string
            enum:
              - order
              - refund
          examples:
            - - order
              - refund
        idSearchType:
          type: string
          description: 搜索字段(单号类), platformOrderId:平台订单号 sellerOrderId:卖家订单号
          enum:
            - platformOrderId
            - sellerOrderId
          examples:
            - platformOrderId
        idSearchMode:
          type: string
          description: 搜索类型(单号类), exact:精确搜索(支持批量) blur:模糊搜索(不支持批量)，默认精确
          enum:
            - exact
            - blur
          examples:
            - exact
        idSearchContents:
          type: array
          description: 搜索内容(单号类)，单个/批量搜索都传数组
          items:
            type: string
          examples:
            - - '1'
              - '2'
        searchType:
          type: string
          description: '搜索字段,productId:产品ID; msku:MSKU; sku:SKU; commodityName:品名; '
          enum:
            - orderId
            - payoutId
            - productId
            - transactionId
            - msku
            - remark
          examples:
            - msku
        searchMode:
          type: string
          description: 搜索类型, exact:精确搜索(支持批量) blur:模糊搜索(不支持批量)，默认精确
          enum:
            - exact
            - blur
          examples:
            - exact
        searchContents:
          type: array
          description: 搜索内容，单个/批量搜索都传数组
          items:
            type: string
          examples:
            - - '1'
              - '2'
        orderBy:
          type: string
          description: >-
            排序字段,
            biz_time,gross_profit,payment_time,shipment_time,purchase_time,quantity,sales_amount,sales_tax,shipping_fee,promotion_saving,cost_purchase_fee,cost_head_trip_fee,cost_freight_fee
          examples:
            - biz_time
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
      title: FinAggShopifySettlementOpenQo
      x-apifox-orders:
        - shopIds
        - dayType
        - startDay
        - endDay
        - currency
        - orderTypes
        - idSearchType
        - idSearchMode
        - idSearchContents
        - searchType
        - searchMode
        - searchContents
        - orderBy
        - desc
        - pageNo
        - pageSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«FinAggSettlementShopifyOpenVO»:
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
          $ref: '#/components/schemas/FinAggSettlementShopifyOpenVO'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«FinAggSettlementShopifyOpenVO»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FinAggSettlementShopifyOpenVO:
      type: object
      properties:
        rows:
          type: array
          items:
            $ref: '#/components/schemas/FinAggSettlementShopifyPageOpenVO'
        totalPage:
          type: integer
          format: int32
          description: 总页数
        totalSize:
          type: integer
          format: int32
          description: 数据总条数
      title: FinAggSettlementShopifyOpenVO
      x-apifox-orders:
        - rows
        - totalPage
        - totalSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FinAggSettlementShopifyPageOpenVO:
      type: object
      properties:
        currency:
          type: string
          description: 币种
        shopId:
          type: integer
          format: int32
          description: 店铺ID
        shopName:
          type: string
          description: 店铺名称
        bizTime:
          type: string
          description: 结算时间
        paymentTime:
          type: string
          description: 支付时间
        shipmentTime:
          type: string
          description: 发货时间
        purchaseTime:
          type: string
          description: 订购时间
        orderType:
          type: string
          description: 交易类型
        platformOrderId:
          type: string
          description: 平台订单号
        sellerOrderId:
          type: string
          description: 卖家订单号
        productId:
          type: string
          description: 产品ID
        msku:
          type: string
          description: MSKU
        sku:
          type: string
          description: SKU
        commodityName:
          type: string
          description: 品名
        grossProfit:
          type: number
          description: 毛利润
        quantity:
          type: integer
          format: int32
          description: 数量
        salesAmount:
          type: number
          description: 销售额
        salesTax:
          type: number
          description: 销售税
        shippingFee:
          type: number
          description: 买家运费
        promotionSaving:
          type: number
          description: 促销折扣
        costPurchaseFee:
          type: number
          description: 采购成本
        costHeadTripFee:
          type: number
          description: 头程费用
        costFreightFee:
          type: number
          description: 物流运费
      title: FinAggSettlementShopifyPageOpenVO
      x-apifox-orders:
        - currency
        - shopId
        - shopName
        - bizTime
        - paymentTime
        - shipmentTime
        - purchaseTime
        - orderType
        - platformOrderId
        - sellerOrderId
        - productId
        - msku
        - sku
        - commodityName
        - grossProfit
        - quantity
        - salesAmount
        - salesTax
        - shippingFee
        - promotionSaving
        - costPurchaseFee
        - costHeadTripFee
        - costFreightFee
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
