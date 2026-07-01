# TikTok利润报表-查询开发员

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/financial/tkReport/queryPageDeveloper.json:
    post:
      summary: TikTok利润报表-查询开发员
      deprecated: false
      description: ''
      operationId: getFinTkPageDeveloperUsingPOST
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
              $ref: '#/components/schemas/TkMskuDaySummaryDeveloperOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABTkReportPageDeveloperOpenVo%C2%BB
          headers: {}
          x-apifox-name: 成功
        '201':
          description: Created
          headers: {}
          x-apifox-name: 成功
        '401':
          description: Unauthorized
          headers: {}
          x-apifox-name: 没有权限
        '403':
          description: Forbidden
          headers: {}
          x-apifox-name: 禁止访问
        '404':
          description: Not Found
          headers: {}
          x-apifox-name: 记录不存在
      security: []
      x-order: '2147483647'
      x-apifox-folder: 多平台/财务
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-365907913-run
components:
  schemas:
    TkMskuDaySummaryDeveloperOpenQo:
      type: object
      required:
        - startDate
        - endDate
      properties:
        startDate:
          type: string
          description: 开始时间
          examples:
            - '2025-08-28'
        endDate:
          type: string
          description: 结束时间
          examples:
            - '2025-09-26'
        shopIds:
          type: array
          description: 店铺ID,格式:4608
          items:
            type: integer
            format: int32
        platformShopTypes:
          type: array
          description: 店铺类型：CROSS_BORDER-跨境
          items:
            type: string
        marketplaceCodes:
          type: array
          description: 站点
          items:
            type: string
          examples:
            - US,CA,UK,AU,NZ,DE,FR,IT,NL
        currency:
          type: string
          description: 币种原币种,原币种传空字符串
          enum:
            - CNY
            - USD
            - EUR
            - GBP
            - IDR
            - SGD
            - MYR
            - THB
            - VND
            - PHP
        orderField:
          type: string
          description: 排序字段,比如:gross_profit
        orderValue:
          type: string
          description: 排序方式,desc/asc
        pageNum:
          type: string
          description: 当前页,默认1
        pageSize:
          type: string
          description: 每页条数,默认20
        developers:
          type: array
          description: 开发员,格式：229,230,231
          items:
            type: string
      title: TkMskuDaySummaryDeveloperOpenQo
      x-apifox-orders:
        - startDate
        - endDate
        - shopIds
        - platformShopTypes
        - marketplaceCodes
        - currency
        - orderField
        - orderValue
        - pageNum
        - pageSize
        - developers
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«TkReportPageDeveloperOpenVo»:
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
          $ref: '#/components/schemas/TkReportPageDeveloperOpenVo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«TkReportPageDeveloperOpenVo»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    TkReportPageDeveloperOpenVo:
      type: object
      properties:
        rows:
          type: array
          items:
            $ref: '#/components/schemas/TkMskuDaySummaryDeveloperOpenVo'
        totalPage:
          type: integer
          format: int32
          description: 总页数
        totalSize:
          type: integer
          format: int32
          description: 数据总条数
      title: TkReportPageDeveloperOpenVo
      x-apifox-orders:
        - rows
        - totalPage
        - totalSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    TkMskuDaySummaryDeveloperOpenVo:
      type: object
      properties:
        developerNameList:
          type: array
          description: 开发员
          items:
            type: string
        shopIds:
          type: string
          description: 店铺ID
        salesQuantity:
          type: integer
          format: int32
          description: 销量
        returnQuantity:
          type: integer
          format: int32
          description: 退款量
        grossProfit:
          type: number
          description: 毛利润
        grossRate:
          type: number
          description: 毛利率
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
        adsCost:
          type: number
          description: 广告花费
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
        purchaseFee:
          type: number
          description: 采购成本
        headFee:
          type: number
          description: 头程费用
        logisticsFee:
          type: number
          description: 物流运费
        shopOtherFee:
          type: number
          description: 自定义店铺费用
        asinOtherFee:
          type: number
          description: 自定义产品费用
        currency:
          type: string
          description: 币种
        evaluationPrincipal:
          type: number
          description: 测评本金
        evaluationCommission:
          type: number
          description: 测评佣金
        evaluationFee:
          type: number
          description: 测评费用
      title: TkMskuDaySummaryDeveloperOpenVo
      x-apifox-orders:
        - developerNameList
        - shopIds
        - salesQuantity
        - returnQuantity
        - grossProfit
        - grossRate
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
        - adsCost
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
        - purchaseFee
        - headFee
        - logisticsFee
        - shopOtherFee
        - asinOtherFee
        - currency
        - evaluationPrincipal
        - evaluationCommission
        - evaluationFee
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
