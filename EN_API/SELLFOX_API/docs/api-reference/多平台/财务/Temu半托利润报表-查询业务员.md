# Temu半托利润报表-查询业务员

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/financial/cross/temuPartReport/queryPageSalesMan.json:
    post:
      summary: Temu半托利润报表-查询业务员
      deprecated: false
      description: ''
      operationId: getFinTemuPageSalesManUsingPOST_1
      tags:
        - 多平台/财务
        - Temu半托利润报表
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
              $ref: '#/components/schemas/TemuPartMskuDaySummarySalesManOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABTemuPartReportPageSalesManOpenVo%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-365907910-run
components:
  schemas:
    TemuPartMskuDaySummarySalesManOpenQo:
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
        salesMans:
          type: array
          description: 业务员,多个批量查询，格式：13522
          items:
            type: string
      title: TemuPartMskuDaySummarySalesManOpenQo
      x-apifox-orders:
        - startDate
        - endDate
        - shopIds
        - currency
        - orderField
        - orderValue
        - pageNum
        - pageSize
        - salesMans
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«TemuPartReportPageSalesManOpenVo»:
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
          $ref: '#/components/schemas/TemuPartReportPageSalesManOpenVo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«TemuPartReportPageSalesManOpenVo»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    TemuPartReportPageSalesManOpenVo:
      type: object
      properties:
        rows:
          type: array
          items:
            $ref: '#/components/schemas/TemuPartMskuDaySummarySalesManOpenVo'
        totalPage:
          type: integer
          format: int32
          description: 总页数
        totalSize:
          type: integer
          format: int32
          description: 数据总条数
      title: TemuPartReportPageSalesManOpenVo
      x-apifox-orders:
        - rows
        - totalPage
        - totalSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    TemuPartMskuDaySummarySalesManOpenVo:
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
        salesNum:
          type: number
          description: 销量
        refundQuantity:
          type: integer
          format: int32
          description: 退款量
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
        freightFee:
          type: number
          description: 运费收入
        eprRefundFee:
          type: number
          description: ERP费用(已退费)
        platformExpendFee:
          type: number
          description: 平台支出合计
        refundAfterFee:
          type: number
          description: 售后退款
        freightRefundFee:
          type: number
          description: 运费退款
        violationFee:
          type: number
          description: 履约违规
        fraudulentFee:
          type: number
          description: 欺诈发货费
        buyerRefusesFee:
          type: number
          description: 买家拒付
        consumerSettlementFee:
          type: number
          description: 消费者和解费
        shippingLabelFee:
          type: number
          description: 发货面单费
        returnLabelFee:
          type: number
          description: 退货面单费
        advertisingServiceFee:
          type: number
          description: 广告服务费
        taxesWithholdFee:
          type: number
          description: 税金代扣
        taxesReturnFee:
          type: number
          description: 税金退回
        eprWithholdFee:
          type: number
          description: ERP费用(已扣费)
        storeOtherExpend:
          type: number
          description: 店铺其他账务
        purchaseFee:
          type: number
          description: 采购成本
        headTripFee:
          type: number
          description: 头程费用
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
        evaluationPrincipal:
          type: number
          description: 测评本金
        evaluationCommission:
          type: number
          description: 测评佣金
        evaluationFee:
          type: number
          description: 测评费用
      title: TemuPartMskuDaySummarySalesManOpenVo
      x-apifox-orders:
        - salesManNameList
        - shopId
        - salesNum
        - refundQuantity
        - grossProfit
        - grossRate
        - repaymentAmount
        - platformIncomeFee
        - transactionFee
        - freightFee
        - eprRefundFee
        - platformExpendFee
        - refundAfterFee
        - freightRefundFee
        - violationFee
        - fraudulentFee
        - buyerRefusesFee
        - consumerSettlementFee
        - shippingLabelFee
        - returnLabelFee
        - advertisingServiceFee
        - taxesWithholdFee
        - taxesReturnFee
        - eprWithholdFee
        - storeOtherExpend
        - purchaseFee
        - headTripFee
        - logisticsFee
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
