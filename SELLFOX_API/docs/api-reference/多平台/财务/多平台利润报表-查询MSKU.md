# 多平台利润报表-查询MSKU

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/financial/aggReport/queryPageMsku.json:
    post:
      summary: 多平台利润报表-查询MSKU
      deprecated: false
      description: ''
      operationId: getFinTemuPageMskuUsingPOST
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
              $ref: '#/components/schemas/FinAggMskuSummaryMskuOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABFinAggReportPageMskuOpenVo%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-365907900-run
components:
  schemas:
    FinAggMskuSummaryMskuOpenQo:
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
          description: 排序字段,比如:income_sales_fee
        orderValue:
          type: string
          description: 排序方式,desc/asc
        pageNo:
          type: string
          description: 当前页,默认1
        pageSize:
          type: string
          description: 每页条数,默认20
        platformTypes:
          type: array
          description: >-
            平台类型,比如:HALF_TEMU,ALL_TEMU,WALMART,TIKTOK,HALF_SHEIN,SELF_SHEIN,AGENT_SHEIN,SHOPIFY,ALIEXPRESS_POP_CHOICE,EBAY,MERCADO,SHOPEE
          items:
            type: string
        searchField:
          type: string
          description: 过滤字段名称 msku：msku
        searchType:
          type: string
          description: 过滤字段模式 blur：模糊查询 exact：精确查询
        searchValue:
          type: string
          description: 过滤字段值 MSKU：shopee-Test5
      title: FinAggMskuSummaryMskuOpenQo
      x-apifox-orders:
        - startDate
        - endDate
        - shopIds
        - currency
        - orderField
        - orderValue
        - pageNo
        - pageSize
        - platformTypes
        - searchField
        - searchType
        - searchValue
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«FinAggReportPageMskuOpenVo»:
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
          $ref: '#/components/schemas/FinAggReportPageMskuOpenVo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«FinAggReportPageMskuOpenVo»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FinAggReportPageMskuOpenVo:
      type: object
      properties:
        rows:
          type: array
          items:
            $ref: '#/components/schemas/FinAggMskuDaySummaryMskuOpenVo'
        totalPage:
          type: integer
          format: int32
          description: 总页数
        totalSize:
          type: integer
          format: int32
          description: 数据总条数
      title: FinAggReportPageMskuOpenVo
      x-apifox-orders:
        - rows
        - totalPage
        - totalSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FinAggMskuDaySummaryMskuOpenVo:
      type: object
      properties:
        platformName:
          type: string
          description: 平台
        shopId:
          type: string
          description: 店铺ID
        shopName:
          type: string
          description: 店铺
        salesNum:
          type: integer
          format: int32
          description: 销量
        sku:
          type: string
          description: SKU
        commodityName:
          type: string
          description: 品名
        refundNum:
          type: integer
          format: int32
          description: 退款量
        grossProfit:
          type: number
          description: 毛利润
        msku:
          type: string
          description: MSKU
        grossProfitMargin:
          type: number
          description: 毛利率
        image:
          type: string
          description: 图片
        developerNameList:
          type: array
          description: 开发员
          items:
            type: string
        repaymentAmount:
          type: number
          description: 回款额
        incomeSalesFee:
          type: number
          description: 销售额
        salesManNameList:
          type: array
          description: 业务员
          items:
            type: string
        incomeNetSalesFee:
          type: number
          description: 净销售额
        incomeShippingFee:
          type: number
          description: 买家运费
        incomeSellerProductDiscountFee:
          type: number
          description: 卖家商品折扣
        incomePlatformProductDiscountFee:
          type: number
          description: 平台商品折扣
        incomeSellerShippingDiscountFee:
          type: number
          description: 卖家运费折扣
        incomePlatformShippingDiscountFee:
          type: number
          description: 平台运费折扣
        incomeCompensationFee:
          type: number
          description: 赔偿收入
        incomeOtherFee:
          type: number
          description: 其他收入
        incomeRefundFee:
          type: number
          description: 收入退款额
        incomeExpensesRefundFee:
          type: number
          description: 费用退款额
        expendPlatformFee:
          type: number
          description: 平台费
        expendDeliveryFee:
          type: number
          description: 配送费
        expendAdvertisingFee:
          type: number
          description: 广告花费
        expendStorageFee:
          type: number
          description: 仓储费
        expendPromotionFee:
          type: number
          description: 推广费
        expendAdjustFee:
          type: number
          description: 调整
        expendPlatformFinesFee:
          type: number
          description: 平台罚款
        expendOtherFee:
          type: number
          description: 其他支出
        taxSaleFee:
          type: number
          description: 销售税
        taxMarketFee:
          type: number
          description: 市场税
        taxOtherFee:
          type: number
          description: 其他税费
        costPurchaseFee:
          type: number
          description: 采购成本
        costHeadTripFee:
          type: number
          description: 头程费用
        costFreightFee:
          type: number
          description: 物流运费
        shopOtherFee:
          type: number
          description: 自定义店铺费用
        productOtherFee:
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
      title: FinAggMskuDaySummaryMskuOpenVo
      x-apifox-orders:
        - platformName
        - shopId
        - shopName
        - salesNum
        - sku
        - commodityName
        - refundNum
        - grossProfit
        - msku
        - grossProfitMargin
        - image
        - developerNameList
        - repaymentAmount
        - incomeSalesFee
        - salesManNameList
        - incomeNetSalesFee
        - incomeShippingFee
        - incomeSellerProductDiscountFee
        - incomePlatformProductDiscountFee
        - incomeSellerShippingDiscountFee
        - incomePlatformShippingDiscountFee
        - incomeCompensationFee
        - incomeOtherFee
        - incomeRefundFee
        - incomeExpensesRefundFee
        - expendPlatformFee
        - expendDeliveryFee
        - expendAdvertisingFee
        - expendStorageFee
        - expendPromotionFee
        - expendAdjustFee
        - expendPlatformFinesFee
        - expendOtherFee
        - taxSaleFee
        - taxMarketFee
        - taxOtherFee
        - costPurchaseFee
        - costHeadTripFee
        - costFreightFee
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
