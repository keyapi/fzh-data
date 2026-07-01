# 多平台利润报表-查询结算明细-MercadoLibre

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/financial/aggReport/settlement/mercadoLibrePage.json:
    post:
      summary: 多平台利润报表-查询结算明细-MercadoLibre
      deprecated: false
      description: ''
      operationId: settlementMercadoLibrePageUsingPOST
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
              $ref: '#/components/schemas/FinAggMercadoSettlementOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABFinAggSettlementMercadoOpenVO%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-426459616-run
components:
  schemas:
    FinAggMercadoSettlementOpenQo:
      type: object
      required:
        - startDate
        - endDate
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
        marketplaceCodes:
          type: array
          description: 站点
          items:
            type: string
          examples:
            - - '1'
              - '2'
              - '3'
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
        currency:
          type: string
          description: 币种，原币种传空字符串
          enum:
            - CNY
            - USD
            - MXN
            - BRL
            - CLP
            - COP
            - ARS
        transactionTypes:
          type: array
          description: 交易类型，Release或者Initial available balance或者Available balance
          items:
            type: string
            enum:
              - Release
              - Initial available balance
              - Available balance
          examples:
            - - Release
              - Initial available balance
        transactionDescriptions:
          type: array
          description: >-
            交易描述, payment:付款; shipping_fee:运费; refund:退款;
            canceled_shipping_fee:运费取消; mediation:调解; mediation_cancel:调解取消;
            reserve_for_dispute:争议预留; reserve_for_bpp_shipping_return:BPP退回预留;
            reserve_for_refund:退款预留; cashback:现金返还;
            reserve_for_debt_payment:债务支付预留; reserve_for_payment:付款预留;
            reserve_for_payout:支出预留; cash_withdrawal:提现;
            reserve_for_a_specific_time_period:特定时间预留;
          items:
            type: string
            enum:
              - payment
              - shipping_fee
              - refund
              - canceled_shipping_fee
              - mediation
              - mediation_cancel
              - reserve_for_dispute
              - reserve_for_bpp_shipping_return
              - reserve_for_refund
              - cashback
              - reserve_for_debt_payment
              - reserve_for_payment
              - reserve_for_payout
              - cash_withdrawal
              - reserve_for_a_specific_time_period
          examples:
            - - payment
              - shipping_fee
        idSearchType:
          type: string
          description: 搜索字段(单号类), statementId:结算编号 orderId:订单号
          enum:
            - statementId
            - orderId
          examples:
            - statementId
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
          description: 搜索字段
          enum:
            - msku
            - sku
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
            排序字段，statement_time,sales_quantity,return_quantity,platform_sku,settlement_amount,sales_amount,commission_amount,finance_amount,platform_delivery_amount,tax_amount,discount_amount,storage_amount,ad_amount,reserve_amount,cash_return_amount,other_amount,balance_amount,cost_amount,head_trip_amount,freight_amount,buyer_freight_amount,net_credit_amount,net_debit_amount
          examples:
            - statement_time
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
      title: FinAggMercadoSettlementOpenQo
      x-apifox-orders:
        - shopIds
        - marketplaceCodes
        - startDate
        - endDate
        - currency
        - transactionTypes
        - transactionDescriptions
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
    OpenResult«FinAggSettlementMercadoOpenVO»:
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
          $ref: '#/components/schemas/FinAggSettlementMercadoOpenVO'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«FinAggSettlementMercadoOpenVO»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FinAggSettlementMercadoOpenVO:
      type: object
      properties:
        rows:
          type: array
          items:
            $ref: '#/components/schemas/FinAggSettlementMercadoPageOpenVO'
        totalPage:
          type: integer
          format: int32
          description: 总页数
        totalSize:
          type: integer
          format: int32
          description: 数据总条数
      title: FinAggSettlementMercadoOpenVO
      x-apifox-orders:
        - rows
        - totalPage
        - totalSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FinAggSettlementMercadoPageOpenVO:
      type: object
      properties:
        currency:
          type: string
          description: 币种
        shopId:
          type: string
          description: 店铺ID
        shopName:
          type: string
          description: 店铺
        marketplaceName:
          type: string
          description: 站点
        transactionType:
          type: string
          description: 交易类型
        transactionDesc:
          type: string
          description: 交易描述
        sourceId:
          type: string
          description: SOURCE ID
        statementId:
          type: string
          description: 结算编号
        orderId:
          type: string
          description: 订单号
        packId:
          type: string
          description: PACK ID
        statementTime:
          type: string
          description: 结算时间
        salesQuantity:
          type: integer
          format: int32
          description: 销量
        returnQuantity:
          type: integer
          format: int32
          description: 退款量
        msku:
          type: string
          description: MSKU
        commodityName:
          type: string
          description: 品名,多个逗号拼接，比如：品名1,品名2
        commoditySku:
          type: string
          description: SKU,多个逗号拼接，比如：sku1,sku2
        commodityInfos:
          type: array
          description: 品名/SKU集合
          items:
            $ref: '#/components/schemas/CommodityInfoVo'
        settlementAmount:
          type: number
          description: 结算金额
        netCreditAmount:
          type: number
          description: 贷方金额
        netDebitAmount:
          type: number
          description: 借方金额
        salesAmount:
          type: number
          description: 销售额
        buyerFreightAmount:
          type: number
          description: 买家运费
        commissionAmount:
          type: number
          description: 佣金
        financeAmount:
          type: number
          description: 融资费
        platformDeliveryAmount:
          type: number
          description: 平台派送费
        taxAmount:
          type: number
          description: 税费
        storageAmount:
          type: number
          description: 仓储费
        adAmount:
          type: number
          description: 广告费
        cashReturnAmount:
          type: number
          description: 现金返还
        otherAmount:
          type: number
          description: 其他
        discountAmount:
          type: number
          description: 优惠金额
        reserveAmount:
          type: number
          description: 预留
        balanceAmount:
          type: number
          description: 余额
        costAmount:
          type: number
          description: 采购成本
        headTripAmount:
          type: number
          description: 头程费用
        freightAmount:
          type: number
          description: 物流运费
      title: FinAggSettlementMercadoPageOpenVO
      x-apifox-orders:
        - currency
        - shopId
        - shopName
        - marketplaceName
        - transactionType
        - transactionDesc
        - sourceId
        - statementId
        - orderId
        - packId
        - statementTime
        - salesQuantity
        - returnQuantity
        - msku
        - commodityName
        - commoditySku
        - commodityInfos
        - settlementAmount
        - netCreditAmount
        - netDebitAmount
        - salesAmount
        - buyerFreightAmount
        - commissionAmount
        - financeAmount
        - platformDeliveryAmount
        - taxAmount
        - storageAmount
        - adAmount
        - cashReturnAmount
        - otherAmount
        - discountAmount
        - reserveAmount
        - balanceAmount
        - costAmount
        - headTripAmount
        - freightAmount
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    CommodityInfoVo:
      type: object
      properties:
        commodityName:
          type: string
          description: 品名
        commoditySku:
          type: string
          description: SKU
      title: CommodityInfoVo
      x-apifox-orders:
        - commodityName
        - commoditySku
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
