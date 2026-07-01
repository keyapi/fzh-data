# TikTok利润报表-查询账单明细

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/financial/tkReport/queryStatementDetail.json:
    post:
      summary: TikTok利润报表-查询账单明细
      deprecated: false
      description: ''
      operationId: queryStatementDetailUsingPOST
      tags:
        - 多平台/财务
        - TikTok利润报表
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
              $ref: '#/components/schemas/FinAggTkSettlementOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABFinAggSettlementTkOpenVO%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-426461067-run
components:
  schemas:
    FinAggTkSettlementOpenQo:
      type: object
      required:
        - timeSearchField
        - startDate
        - endDate
      properties:
        marketplaceCodes:
          type: array
          description: 站点
          items:
            type: string
          examples:
            - - '1'
              - '2'
              - '3'
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
        timeSearchField:
          type: string
          description: >-
            时间类型，statementTime:结算时间，paymentCreateTime:支付开始时间，paymentPaidTime:支付成功时间，orderCreateTime:订单订购时间
          enum:
            - statementTime
            - paymentCreateTime
            - paymentPaidTime
            - orderCreateTime
          examples:
            - statementTime
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
        statementStatus:
          type: array
          description: 结算状态
          items:
            type: string
            enum:
              - SETTLED
              - PENDING
              - PROCESSING
              - PAID
              - FAILED
          examples:
            - SETTLED
        orderStatus:
          type: array
          description: >-
            订单状态, Unknown:未知; Pending:未付款; Pending:未付款; Unshipped:待发货;
            PartiallyShipped:部分发货; Shipped:已发货; Shipped:已发货; Shipped:已发货;
            Completed:已完成; Canceled:已取消;
          items:
            type: string
            enum:
              - Unknown
              - Pending
              - Pending
              - Unshipped
              - PartiallyShipped
              - Shipped
              - Shipped
              - Shipped
              - Completed
              - Canceled
          examples:
            - - Unknown
              - Pending
        orderType:
          type: array
          description: >-
            交易类型, ORDER:订单; RESERVE:预留资金; CHARGE_BACK:账单争议退款;
            CUSTOMER_SERVICE_COMPENSATION:客户服务赔偿;
            DEDUCTIONS_INCURRED_BY_SELLER:卖家责任扣款; GMV_PAYMENT_FOR_ADS:GMV支付广告费;
            PLATFORM_COMMISSION_ADJUSTMENT:佣金调整;
            PLATFORM_COMMISSION_COMPENSATION:佣金赔偿; PLATFORM_PENALTY:平台罚款;
            PROMOTION_ADJUSTMENT:促销调整; REBATE:推荐费返点;
            PLATFORM_COMPENSATION:争议申诉赔偿; PLATFORM_REIMBURSEMENT:平台支付退款;
            COFUNDED_CREATOR_REWARDS:创作者奖励费用;
            FBT_WAREHOUSE_SERVICE_FEE:FBT仓储服务费; LOGISTICS_REIMBURSEMENT:物流赔偿;
            SHIPPING_FEE_ADJUSTMENT:运费调整; SHIPPING_FEE_COMPENSATION:运费赔偿;
            SHIPPING_FEE_REBATE:运费返点; SAMPLE_SHIPPING_FEE:样品运费;
            ADJUSTMENT_FROM_SETTLEMENT_ACCOUNT:结算账户调整; WITHHOLDING_TAX:预扣税;
            MARKETING_BENEFIT_PACKAGE_FEE:营销包装费; SELLER_MISSION_REWARD:卖家奖励;
            OTHER_ADJUSTMENT:其他调整;
          items:
            type: string
            enum:
              - ORDER
              - RESERVE
              - CHARGE_BACK
              - CUSTOMER_SERVICE_COMPENSATION
              - DEDUCTIONS_INCURRED_BY_SELLER
              - GMV_PAYMENT_FOR_ADS
              - PLATFORM_COMMISSION_ADJUSTMENT
              - PLATFORM_COMMISSION_COMPENSATION
              - PLATFORM_PENALTY
              - PROMOTION_ADJUSTMENT
              - REBATE
              - PLATFORM_COMPENSATION
              - PLATFORM_REIMBURSEMENT
              - COFUNDED_CREATOR_REWARDS
              - FBT_WAREHOUSE_SERVICE_FEE
              - LOGISTICS_REIMBURSEMENT
              - SHIPPING_FEE_ADJUSTMENT
              - SHIPPING_FEE_COMPENSATION
              - SHIPPING_FEE_REBATE
              - SAMPLE_SHIPPING_FEE
              - ADJUSTMENT_FROM_SETTLEMENT_ACCOUNT
              - WITHHOLDING_TAX
              - MARKETING_BENEFIT_PACKAGE_FEE
              - SELLER_MISSION_REWARD
              - OTHER_ADJUSTMENT
          examples:
            - - ORDER
              - RESERVE
        paymentStatus:
          type: array
          description: 支付状态
          items:
            type: string
            enum:
              - PROCESSING
              - PAID
              - FAILED
          examples:
            - PROCESSING
        isSampleOrder:
          type: boolean
          description: 样品订单，true:样品订单 false:非样品订单， 默认全部
        timeShowOnMarketplace:
          type: boolean
          description: 是否按站点时间搜索，默认false
        searchType:
          type: string
          description: >-
            搜索字段,platformStatementId:结算ID; platformPaymentId:支付ID; orderId:订单号;
            adjustmentId:调整单号; 
          enum:
            - platformStatementId
            - platformPaymentId
            - orderId
            - adjustmentId
          examples:
            - platformStatementId
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
            页面数关时间、数量、金额等字段均可参与排序，常用排序字段：statement_time=结算时间,payment_create_time=支付开始时间,payment_paid_time=支付成功时间,order_create_time=订单订购时间
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
      title: FinAggTkSettlementOpenQo
      x-apifox-orders:
        - marketplaceCodes
        - shopIds
        - currency
        - timeSearchField
        - startDate
        - endDate
        - statementStatus
        - orderStatus
        - orderType
        - paymentStatus
        - isSampleOrder
        - timeShowOnMarketplace
        - searchType
        - searchMode
        - searchContents
        - orderBy
        - desc
        - pageNo
        - pageSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«FinAggSettlementTkOpenVO»:
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
          $ref: '#/components/schemas/FinAggSettlementTkOpenVO'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«FinAggSettlementTkOpenVO»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FinAggSettlementTkOpenVO:
      type: object
      properties:
        rows:
          type: array
          items:
            $ref: '#/components/schemas/FinAggSettlementTkPageOpenVO'
        totalPage:
          type: integer
          format: int32
          description: 总页数
        totalSize:
          type: integer
          format: int32
          description: 数据总条数
      title: FinAggSettlementTkOpenVO
      x-apifox-orders:
        - rows
        - totalPage
        - totalSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FinAggSettlementTkPageOpenVO:
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
          description: 店铺名称,多个逗号拼接；比如：店铺1,店铺2
        shopNameList:
          type: array
          description: 店铺名称集合
          items:
            type: string
        shopType:
          type: string
          description: 店铺类型 跨境店铺/本土店铺
        marketplaceId:
          type: string
          description: 站点id
        marketplaceName:
          type: string
          description: 站点名称
        marketplaceNameList:
          type: array
          description: 站点名称,多个逗号拼接；比如：站点1,站点2
          items:
            type: string
        shopInfos:
          type: array
          description: 店铺、站点信息集合
          items:
            $ref: '#/components/schemas/ShopMarketPlaceVo'
        statementTime:
          type: string
          format: date-time
          description: 结算时间
        statementId:
          type: string
          description: 结算ID
        paymentId:
          type: string
          description: 支付ID
        statementStatus:
          type: string
          description: 结算状态,SETTLED/PENDING/PROCESSING/PAID/FAILED
        paymentStatus:
          type: string
          description: 支付状态,PROCESSING/PAID/FAILED
        orderStatus:
          type: string
          description: 订单状态, 未付款/待发货/部分发货/已发货/已完成/已取消
        paymentCreateTime:
          type: string
          format: date-time
          description: 支付开始时间
        paymentPaidTime:
          type: string
          format: date-time
          description: 支付成功时间
        orderType:
          type: string
          description: >-
            交易类型,
            订单/预留资金/账单争议退款/客户服务赔偿/卖家责任扣款/GMV支付广告费/佣金调整/佣金赔偿/平台罚款/促销调整/推荐费返点/争议申诉赔偿/平台支付退款/创作者奖励费用/FBT仓储服务费/物流赔偿/运费调整/运费赔偿/运费返点/样品运费/结算账户调整/预扣税/营销包装费/卖家奖励/其他调整/
        orderId:
          type: string
          description: 订单号
        salesQuantity:
          type: integer
          format: int32
          description: 销量
        returnQuantity:
          type: integer
          format: int32
          description: 退款量
        orderCreateTime:
          type: string
          format: date-time
          description: 订单订购时间
        settlementAmount:
          type: number
          description: 结算金额
        grossSalesAmount:
          type: number
          description: 销售额
        grossSalesRefundAmount:
          type: number
          description: 销售额退款
        sellerDiscountAmount:
          type: number
          description: 促销折扣
        sellerDiscountRefundAmount:
          type: number
          description: 促销折扣退款
        codServiceFeeAmount:
          type: number
          description: 货到付款费
        codServiceFeeRefundAmount:
          type: number
          description: 货到付款费退款
        actualShippingFeeAmount:
          type: number
          description: 平台实际运费
        shippingFeeDiscountAmount:
          type: number
          description: 运费折扣
        customerPaidShippingFeeAmount:
          type: number
          description: 买家支付运费
        returnShippingFeeAmount:
          type: number
          description: 退货运费
        replacementShippingFeeAmount:
          type: number
          description: 补发运费
        exchangeShippingFeeAmount:
          type: number
          description: 换货运费
        signatureConfirmationFeeAmount:
          type: number
          description: 物流签收费
        shippingInsuranceFeeAmount:
          type: number
          description: 运输保险费
        returnShippingLabelFeeAmount:
          type: number
          description: 退货标签费
        platformCommissionAmount:
          type: number
          description: 佣金
        referralFeeAmount:
          type: number
          description: 推荐费
        refundAdministrationFeeAmount:
          type: number
          description: 退款管理费
        transactionFeeAmount:
          type: number
          description: 交易费
        creditCardHandlingFeeAmount:
          type: number
          description: 信用卡手续费
        affiliateCommissionAmount:
          type: number
          description: 创作者佣金
        affiliateCommissionAmountBeforePit:
          type: number
          description: 联盟广告佣金
        affiliatePartnerCommissionAmount:
          type: number
          description: 联盟伙伴佣金
        affiliateAdsCommissionAmount:
          type: number
          description: 广告订单佣金
        sfpServiceFeeAmount:
          type: number
          description: 免运费计划费
        liveSpecialsFeeAmount:
          type: number
          description: LIVE费
        bonusCashbackServiceFeeAmount:
          type: number
          description: 奖励现金费
        mallServiceFeeAmount:
          type: number
          description: 商城服务费用
        voucherXtraServiceFeeAmount:
          type: number
          description: Voucher费
        flashSalesServiceFeeAmount:
          type: number
          description: 闪购服务费
        cofundedPromotionServiceFeeAmount:
          type: number
          description: 促销活动费
        preOrderServiceFeeAmount:
          type: number
          description: 预购计划费
        tspCommissionAmount:
          type: number
          description: TSP佣金
        dtHandlingFeeAmount:
          type: number
          description: DT手续费
        eprPobServiceFeeAmount:
          type: number
          description: EPR费
        sellerPaylaterHandlingFeeAmount:
          type: number
          description: PayLater费
        platformOtherServiceFeeAmount:
          type: number
          description: 平台其他费
        vatAmount:
          type: number
          description: VAT税
        importVatAmount:
          type: number
          description: 进口增值税
        customsDutyAmount:
          type: number
          description: 跨境关税
        customsClearanceAmount:
          type: number
          description: 清关费
        sstAmount:
          type: number
          description: SST税
        gstAmount:
          type: number
          description: GST税
        ivaAmount:
          type: number
          description: 墨西哥增值税
        isrAmount:
          type: number
          description: 墨西哥联邦税
        antiDumpingDutyAmount:
          type: number
          description: 反倾销税
        localVatAmount:
          type: number
          description: 代缴增值税
        pitAmount:
          type: number
          description: 代缴PIT税
        adjustmentAmount:
          type: number
          description: 调整费
        adjustmentId:
          type: string
          description: 调整单号
        purchaseFee:
          type: number
          description: 采购成本
        headFee:
          type: number
          description: 头程费用
        logisticsFee:
          type: number
          description: 物流运费
      title: FinAggSettlementTkPageOpenVO
      x-apifox-orders:
        - currency
        - shopId
        - shopName
        - shopNameList
        - shopType
        - marketplaceId
        - marketplaceName
        - marketplaceNameList
        - shopInfos
        - statementTime
        - statementId
        - paymentId
        - statementStatus
        - paymentStatus
        - orderStatus
        - paymentCreateTime
        - paymentPaidTime
        - orderType
        - orderId
        - salesQuantity
        - returnQuantity
        - orderCreateTime
        - settlementAmount
        - grossSalesAmount
        - grossSalesRefundAmount
        - sellerDiscountAmount
        - sellerDiscountRefundAmount
        - codServiceFeeAmount
        - codServiceFeeRefundAmount
        - actualShippingFeeAmount
        - shippingFeeDiscountAmount
        - customerPaidShippingFeeAmount
        - returnShippingFeeAmount
        - replacementShippingFeeAmount
        - exchangeShippingFeeAmount
        - signatureConfirmationFeeAmount
        - shippingInsuranceFeeAmount
        - returnShippingLabelFeeAmount
        - platformCommissionAmount
        - referralFeeAmount
        - refundAdministrationFeeAmount
        - transactionFeeAmount
        - creditCardHandlingFeeAmount
        - affiliateCommissionAmount
        - affiliateCommissionAmountBeforePit
        - affiliatePartnerCommissionAmount
        - affiliateAdsCommissionAmount
        - sfpServiceFeeAmount
        - liveSpecialsFeeAmount
        - bonusCashbackServiceFeeAmount
        - mallServiceFeeAmount
        - voucherXtraServiceFeeAmount
        - flashSalesServiceFeeAmount
        - cofundedPromotionServiceFeeAmount
        - preOrderServiceFeeAmount
        - tspCommissionAmount
        - dtHandlingFeeAmount
        - eprPobServiceFeeAmount
        - sellerPaylaterHandlingFeeAmount
        - platformOtherServiceFeeAmount
        - vatAmount
        - importVatAmount
        - customsDutyAmount
        - customsClearanceAmount
        - sstAmount
        - gstAmount
        - ivaAmount
        - isrAmount
        - antiDumpingDutyAmount
        - localVatAmount
        - pitAmount
        - adjustmentAmount
        - adjustmentId
        - purchaseFee
        - headFee
        - logisticsFee
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ShopMarketPlaceVo:
      type: object
      properties:
        shopName:
          type: string
          description: 店铺名称
        marketplaceName:
          type: string
          description: 站点名称
      title: ShopMarketPlaceVo
      x-apifox-orders:
        - shopName
        - marketplaceName
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
