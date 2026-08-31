# Walmart利润报表-查询业务员

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/financial/walmartReport/queryPageSalesMan.json:
    post:
      summary: Walmart利润报表-查询业务员
      deprecated: false
      description: ''
      operationId: getFinWalmartPageSalesManUsingPOST
      tags:
        - 多平台/财务
        - Walmart利润报表
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
              $ref: '#/components/schemas/WalmartMskuDaySummarySalesManOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABWalmartReportPageSalesManOpenVo%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-365907920-run
components:
  schemas:
    WalmartMskuDaySummarySalesManOpenQo:
      type: object
      required:
        - transactionPostedStartDate
        - transactionPostedEndDate
      properties:
        transactionPostedStartDate:
          type: string
          description: 开始时间
          examples:
            - '2025-08-28'
        transactionPostedEndDate:
          type: string
          description: 结束时间
          examples:
            - '2025-09-26'
        shopId:
          type: array
          description: 店铺ID,格式:4608
          items:
            type: integer
            format: int32
        marketplaceCode:
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
        pageNo:
          type: string
          description: 当前页,默认1
        pageSize:
          type: string
          description: 每页条数,默认20
        salesManIds:
          type: array
          description: 业务员,多个批量查询，格式：13522
          items:
            type: string
      title: WalmartMskuDaySummarySalesManOpenQo
      x-apifox-orders:
        - transactionPostedStartDate
        - transactionPostedEndDate
        - shopId
        - marketplaceCode
        - currency
        - orderField
        - orderValue
        - pageNo
        - pageSize
        - salesManIds
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«WalmartReportPageSalesManOpenVo»:
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
          $ref: '#/components/schemas/WalmartReportPageSalesManOpenVo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«WalmartReportPageSalesManOpenVo»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    WalmartReportPageSalesManOpenVo:
      type: object
      properties:
        rows:
          type: array
          items:
            $ref: '#/components/schemas/WalmartMskuDaySummarySalesManOpenVo'
        totalPage:
          type: integer
          format: int32
          description: 总页数
        totalSize:
          type: integer
          format: int32
          description: 数据总条数
      title: WalmartReportPageSalesManOpenVo
      x-apifox-orders:
        - rows
        - totalPage
        - totalSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    WalmartMskuDaySummarySalesManOpenVo:
      type: object
      properties:
        salesManNameList:
          type: array
          description: 业务员
          items:
            type: string
        shopId:
          type: string
          description: 店铺ID
        salesQty:
          type: integer
          format: int32
          description: 销量
        refundQty:
          type: integer
          format: int32
          description: 退款量
        grossProfit:
          type: number
          description: 毛利润
        grossRate:
          type: number
          description: 毛利率
        totalCollectionAmount:
          type: number
          description: 回款额
        totalIncomeAmount:
          type: number
          description: 收入总额
        salesAmount:
          type: number
          description: 销售额
        productTax:
          type: number
          description: 产品代收税
        productWithheldTax:
          type: number
          description: 产品代缴税
        buyerShippingFee:
          type: number
          description: 买家运费
        buyerShippingFeeTax:
          type: number
          description: 买家运费税
        buyerShippingFeeTaxPay:
          type: number
          description: 买家运费税代缴
        buyerShippingFeeCommission:
          type: number
          description: 买家运费佣金
        commissionAmount:
          type: number
          description: 佣金净额
        promotionSaving:
          type: number
          description: 促销折扣
        walmartFundedSaving:
          type: number
          description: 沃尔玛补贴
        otherTax:
          type: number
          description: 其他税费
        extraDiscountSaving:
          type: number
          description: 额外折扣
        totalRefundAmount:
          type: number
          description: 退款总额
        salesRefundAmount:
          type: number
          description: 销售额退款
        refundProductTax:
          type: number
          description: 退款产品代收税
        refundProductWithheldTax:
          type: number
          description: 退款产品代缴税
        buyerShippingFeeRefund:
          type: number
          description: 买家运费退款
        buyerShippingFeeTaxRefund:
          type: number
          description: 买家运费税退款
        buyerShippingFeeTaxPayRefund:
          type: number
          description: 买家运费税代缴退款
        buyerShippingFeeCommissionRefund:
          type: number
          description: 买家运费佣金退款
        refundCommissionAmount:
          type: number
          description: 退款净佣金
        promotionDiscountRefund:
          type: number
          description: 促销折扣退款
        extraRefundDiscountAmount:
          type: number
          description: 额外促销退款
        walmartFundedSavingAmount:
          type: number
          description: 沃尔玛补贴退款
        excessRefundAdjustmentAmount:
          type: number
          description: 过度退款调整
        refundOtherTax:
          type: number
          description: 其他税费退款
        totalAdjustmentAmount:
          type: number
          description: 调整总额
        wfsDamageWarehouseAmount:
          type: number
          description: WFS仓库损坏
        wfsRefundAmount:
          type: number
          description: WFS退款
        wfsLostInventoryAmount:
          type: number
          description: WFS丢失赔偿
        wfsFoundInventoryAmount:
          type: number
          description: WFS库存找回
        wfsChargeAmount:
          type: number
          description: WFS收费
        wfsReturnShippingAmount:
          type: number
          description: WFS退回运费
        wfsFulfillmentAmount:
          type: number
          description: WFS配送费
        commissionAdjustmentAmount:
          type: number
          description: 佣金调整
        businessCompensateAmount:
          type: number
          description: 平台特定补偿
        returnReversalAdjustmentAmount:
          type: number
          description: 退款撤销调整
        swwInternationalShippingFee:
          type: number
          description: SWW国际配送费
        totalServiceAmount:
          type: number
          description: 服务费总额
        wfsStorageAmount:
          type: number
          description: WFS仓储费
        wfsPrepServiceAmount:
          type: number
          description: WFS入库费
        wfsInventoryTransferAmount:
          type: number
          description: WFS库存转移费
        wfsRemoveFee:
          type: number
          description: WFS移除费
        wfsLongTermStorageFee:
          type: number
          description: WFS长期仓储费
        advertisingAmount:
          type: number
          description: 广告费
        spAmount:
          type: number
          description: SP
        advertisingDiffAmount:
          type: number
          description: 广告差异分摊
        advertisingCreditsAmount:
          type: number
          description: 广告费抵扣
        reviewAcceleratorAmount:
          type: number
          description: 官方邀评费
        marketingAmount:
          type: number
          description: 推广费
        wfsDisposalAmount:
          type: number
          description: WFS销毁费
        returnReversalAmount:
          type: number
          description: 退款撤销
        otherIncomeAmount:
          type: number
          description: 其他收入
        otherExpendAmount:
          type: number
          description: 其他支出
        costAmount:
          type: number
          description: 采购成本
        headTripAmount:
          type: number
          description: 头程费用
        freightAmount:
          type: number
          description: 物流运费
        shopOtherFee:
          type: number
          description: 店铺其他费
        productOtherFee:
          type: number
          description: 产品其他费
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
      title: WalmartMskuDaySummarySalesManOpenVo
      x-apifox-orders:
        - salesManNameList
        - shopId
        - salesQty
        - refundQty
        - grossProfit
        - grossRate
        - totalCollectionAmount
        - totalIncomeAmount
        - salesAmount
        - productTax
        - productWithheldTax
        - buyerShippingFee
        - buyerShippingFeeTax
        - buyerShippingFeeTaxPay
        - buyerShippingFeeCommission
        - commissionAmount
        - promotionSaving
        - walmartFundedSaving
        - otherTax
        - extraDiscountSaving
        - totalRefundAmount
        - salesRefundAmount
        - refundProductTax
        - refundProductWithheldTax
        - buyerShippingFeeRefund
        - buyerShippingFeeTaxRefund
        - buyerShippingFeeTaxPayRefund
        - buyerShippingFeeCommissionRefund
        - refundCommissionAmount
        - promotionDiscountRefund
        - extraRefundDiscountAmount
        - walmartFundedSavingAmount
        - excessRefundAdjustmentAmount
        - refundOtherTax
        - totalAdjustmentAmount
        - wfsDamageWarehouseAmount
        - wfsRefundAmount
        - wfsLostInventoryAmount
        - wfsFoundInventoryAmount
        - wfsChargeAmount
        - wfsReturnShippingAmount
        - wfsFulfillmentAmount
        - commissionAdjustmentAmount
        - businessCompensateAmount
        - returnReversalAdjustmentAmount
        - swwInternationalShippingFee
        - totalServiceAmount
        - wfsStorageAmount
        - wfsPrepServiceAmount
        - wfsInventoryTransferAmount
        - wfsRemoveFee
        - wfsLongTermStorageFee
        - advertisingAmount
        - spAmount
        - advertisingDiffAmount
        - advertisingCreditsAmount
        - reviewAcceleratorAmount
        - marketingAmount
        - wfsDisposalAmount
        - returnReversalAmount
        - otherIncomeAmount
        - otherExpendAmount
        - costAmount
        - headTripAmount
        - freightAmount
        - shopOtherFee
        - productOtherFee
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
