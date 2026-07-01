# Temu全托利润报表-查询店铺

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/financial/cross/temuAllReport/queryPageShop.json:
    post:
      summary: Temu全托利润报表-查询店铺
      deprecated: false
      description: ''
      operationId: getFinTemuPageShopUsingPOST_1
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
              $ref: '#/components/schemas/TemuAllMskuDaySummaryShopOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABTemuAllReportPageShopOpenVo%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-365907906-run
components:
  schemas:
    TemuAllMskuDaySummaryShopOpenQo:
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
      title: TemuAllMskuDaySummaryShopOpenQo
      x-apifox-orders:
        - startDate
        - endDate
        - shopIds
        - currency
        - orderField
        - orderValue
        - pageNum
        - pageSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«TemuAllReportPageShopOpenVo»:
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
          $ref: '#/components/schemas/TemuAllReportPageShopOpenVo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«TemuAllReportPageShopOpenVo»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    TemuAllReportPageShopOpenVo:
      type: object
      properties:
        rows:
          type: array
          items:
            $ref: '#/components/schemas/TemuAllMskuDaySummaryShopOpenVo'
        totalPage:
          type: integer
          format: int32
          description: 总页数
        totalSize:
          type: integer
          format: int32
          description: 数据总条数
      title: TemuAllReportPageShopOpenVo
      x-apifox-orders:
        - rows
        - totalPage
        - totalSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    TemuAllMskuDaySummaryShopOpenVo:
      type: object
      properties:
        shopId:
          type: string
          description: 店铺ID
        shopNameList:
          type: array
          description: 店铺名称
          items:
            type: string
        platformStoreNoList:
          type: array
          description: 平台店铺编号
          items:
            type: string
        salesNum:
          type: number
          description: 销量
        grossProfit:
          type: number
          description: 毛利润
        grossRate:
          type: number
          description: 毛利率
        repaymentAmount:
          type: number
          description: 回款额
        platformIncomeFee:
          type: number
          description: 平台收入合计
        transactionFee:
          type: number
          description: 交易收入
        consumerRefundFee:
          type: number
          description: 消费者退款
        afterSalesSubsidyFee:
          type: number
          description: 非商责平台售后补贴
        eprRefundFee:
          type: number
          description: ERP费用（已退费）
        platformExpendFee:
          type: number
          description: 平台支出合计
        warehouseServiceFee:
          type: number
          description: 仓储综合服务费
        advertisingServiceFee:
          type: number
          description: 广告服务费
        commercialAfterSalesFee:
          type: number
          description: 非商责平台售后补贴调整
        warehouseAddedServiceFee:
          type: number
          description: 贴标费
        stockDebitFee:
          type: number
          description: 备货违规扣款
        qualityAccidentDebitFee:
          type: number
          description: 质量事故违规扣款
        afterSaleDebitFee:
          type: number
          description: 售后赔付扣款
        productQualityFee:
          type: number
          description: 商品品质保障-质量问题（JIT商品）
        storeOtherExpend:
          type: number
          description: 店铺其他账务
        eprWithholdFee:
          type: number
          description: ERP费用（已扣费）
        purchaseFee:
          type: number
          description: 采购成本
        logisticsFee:
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
      title: TemuAllMskuDaySummaryShopOpenVo
      x-apifox-orders:
        - shopId
        - shopNameList
        - platformStoreNoList
        - salesNum
        - grossProfit
        - grossRate
        - repaymentAmount
        - platformIncomeFee
        - transactionFee
        - consumerRefundFee
        - afterSalesSubsidyFee
        - eprRefundFee
        - platformExpendFee
        - warehouseServiceFee
        - advertisingServiceFee
        - commercialAfterSalesFee
        - warehouseAddedServiceFee
        - stockDebitFee
        - qualityAccidentDebitFee
        - afterSaleDebitFee
        - productQualityFee
        - storeOtherExpend
        - eprWithholdFee
        - purchaseFee
        - logisticsFee
        - shopOtherFee
        - productOtherFee
        - currency
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
