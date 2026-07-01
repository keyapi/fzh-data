# 多平台利润报表-查询结算明细-eBay

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/financial/aggReport/settlement/eBayPage.json:
    post:
      summary: 多平台利润报表-查询结算明细-eBay
      deprecated: false
      description: ''
      operationId: settlementEBayPageUsingPOST
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
              $ref: '#/components/schemas/FinAggEbaySettlementOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABFinAggSettlementEbayOpenVO%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-426459615-run
components:
  schemas:
    FinAggEbaySettlementOpenQo:
      type: object
      required:
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
        hktSearch:
          type: boolean
          description: 是否按HKT时间搜索，true：HKT时间(UTC+8:00) false：UTC时间
          examples:
            - false
        transactionTypes:
          type: array
          description: >-
            交易类型, SALE:销售订单; REFUND:买家退款; CREDIT:卖家账户信用; DISPUTE:付款争议;
            SHIPPING_LABEL:邮寄标签; TRANSFER:转账（报销）; NON_SALE_CHARGE:非订单费用;
            ADJUSTMENT:卖家账户调整; WITHDRAWAL:卖家按需提现; LOAN_REPAYMENT:贷款还款;
            PURCHASE:卖家购买商品;
          items:
            type: string
            enum:
              - SALE
              - REFUND
              - CREDIT
              - DISPUTE
              - SHIPPING_LABEL
              - TRANSFER
              - NON_SALE_CHARGE
              - ADJUSTMENT
              - WITHDRAWAL
              - LOAN_REPAYMENT
              - PURCHASE
          examples:
            - - SALE
              - REFUND
        transactionStatus:
          type: array
          description: >-
            交易状态, FUNDS_ON_HOLD:资金冻结; FUNDS_PROCESSING:处理中;
            FUNDS_AVAILABLE_FOR_PAYOUT:可提现; PAYOUT:已支付; COMPLETED:已完成; FAILED:失败
          items:
            type: string
            enum:
              - FUNDS_ON_HOLD
              - FUNDS_PROCESSING
              - FUNDS_AVAILABLE_FOR_PAYOUT
              - PAYOUT
              - COMPLETED
              - FAILED
          examples:
            - - FUNDS_ON_HOLD
              - FUNDS_PROCESSING
        searchType:
          type: string
          description: >-
            搜索字段,orderId:订单编号; payoutId:发款编号; productId:产品ID;
            transactionId:交易编号; msku:MSKU; remark:备注;
          enum:
            - orderId
            - payoutId
            - productId
            - transactionId
            - msku
            - remark
          examples:
            - orderId
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
            排序字段,sales_num,refund_num,collection_amount,sales_amount,other_income_fee,order_tax,sales_amount_refund,fee_refund,tax_refund,commission_amount,subscription_fee,listing_fee,fulfillment_amount,ads_amount,adjustment_amount,platform_fines_fee,other_fee,not_order_transaction_fee,cost_purchase_fee,cost_head_trip_fee,cost_freight_fee
          examples:
            - sales_num
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
      title: FinAggEbaySettlementOpenQo
      x-apifox-orders:
        - shopIds
        - startDay
        - endDay
        - currency
        - hktSearch
        - transactionTypes
        - transactionStatus
        - searchType
        - searchMode
        - searchContents
        - orderBy
        - desc
        - pageNo
        - pageSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«FinAggSettlementEbayOpenVO»:
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
          $ref: '#/components/schemas/FinAggSettlementEbayOpenVO'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«FinAggSettlementEbayOpenVO»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FinAggSettlementEbayOpenVO:
      type: object
      properties:
        rows:
          type: array
          items:
            $ref: '#/components/schemas/FinAggSettlementEbayPageOpenVO'
        totalPage:
          type: integer
          format: int32
          description: 总页数
        totalSize:
          type: integer
          format: int32
          description: 数据总条数
      title: FinAggSettlementEbayOpenVO
      x-apifox-orders:
        - rows
        - totalPage
        - totalSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FinAggSettlementEbayPageOpenVO:
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
        transactionStatus:
          type: string
          description: 交易状态
        transactionTime:
          type: string
          description: 交易日期
        transactionType:
          type: string
          description: 交易类型
        remark:
          type: string
          description: 描述
        orderId:
          type: string
          description: 订单编号
        payoutId:
          type: string
          description: 发款编号
        transactionId:
          type: string
          description: 交易编号
        productId:
          type: string
          description: 产品ID
        msku:
          type: string
          description: MSKU
        salesNum:
          type: integer
          format: int32
          description: 销量
        refundNum:
          type: integer
          format: int32
          description: 退款量
        collectionAmount:
          type: number
          description: 回款额
        salesAmount:
          type: number
          description: 销售额
        otherIncomeFee:
          type: number
          description: 其他收入
        orderTax:
          type: number
          description: 订单税费
        salesTax:
          type: number
          description: 订单税费-销售税
        otherTax:
          type: number
          description: 订单税费-其他税费
        salesAmountRefund:
          type: number
          description: 销售额退款
        feeRefund:
          type: number
          description: 费用退款
        taxRefund:
          type: number
          description: 税费退款
        commissionAmount:
          type: number
          description: 佣金
        subscriptionFee:
          type: number
          description: 订阅费
        listingFee:
          type: number
          description: 刊登费
        fulfillmentAmount:
          type: number
          description: 配送费
        adsAmount:
          type: number
          description: 广告花费
        adjustmentAmount:
          type: number
          description: 调整
        platformFinesFee:
          type: number
          description: 平台罚款
        otherFee:
          type: number
          description: 其他费用
        notOrderTransactionFee:
          type: number
          description: 非订单交易费
        costPurchaseFee:
          type: number
          description: 采购成本
        costHeadTripFee:
          type: number
          description: 头程费用
        costFreightFee:
          type: number
          description: 物流运费
      title: FinAggSettlementEbayPageOpenVO
      x-apifox-orders:
        - currency
        - shopId
        - shopName
        - transactionStatus
        - transactionTime
        - transactionType
        - remark
        - orderId
        - payoutId
        - transactionId
        - productId
        - msku
        - salesNum
        - refundNum
        - collectionAmount
        - salesAmount
        - otherIncomeFee
        - orderTax
        - salesTax
        - otherTax
        - salesAmountRefund
        - feeRefund
        - taxRefund
        - commissionAmount
        - subscriptionFee
        - listingFee
        - fulfillmentAmount
        - adsAmount
        - adjustmentAmount
        - platformFinesFee
        - otherFee
        - notOrderTransactionFee
        - costPurchaseFee
        - costHeadTripFee
        - costFreightFee
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
