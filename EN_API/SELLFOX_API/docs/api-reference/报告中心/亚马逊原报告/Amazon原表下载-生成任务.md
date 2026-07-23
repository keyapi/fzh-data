# Amazon原表下载-生成任务

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/report/center/add.json:
    post:
      summary: Amazon原表下载-生成任务
      deprecated: false
      description: ''
      operationId: addUsingPOST_1
      tags:
        - 报告中心/亚马逊原报告
        - 数据
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
              $ref: '#/components/schemas/ReportCenterAddParamOpenVo'
            example: ''
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: '#/components/schemas/OpenResult%C2%ABIdData%C2%BB'
          headers: {}
          x-apifox-name: 成功
        '201':
          description: Created
          content:
            '*/*':
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: 成功
        '401':
          description: Unauthorized
          content:
            '*/*':
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: 没有权限
        '403':
          description: Forbidden
          content:
            '*/*':
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: 禁止访问
        '404':
          description: Not Found
          content:
            '*/*':
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: 记录不存在
      security: []
      x-apifox-folder: 报告中心/亚马逊原报告
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-52761476-run
components:
  schemas:
    ReportCenterAddParamOpenVo:
      type: object
      required:
        - title
        - shopId
        - reportType
        - startDate
        - endDate
      properties:
        title:
          type: string
          description: 报告名称
        shopId:
          type: string
          description: 店铺ID
        reportType:
          type: string
          description: >-
            报告类型，可选值：<br/>库存：<br/>inventory:盘库报告<br/>fbaFulfillmentMonthlyInventoryData:每月库存历史记录<br/>fbaFulfillmentCurrentInventoryData:每日库存历史记录<br/>fbaFulfillmentInventoryReceiptsData:已接收库存<br/>fbaInventoryPlanningData:亚马逊物流管理库存状况报告<br/>ledgerDetailViewData:库存分类账报表-详细视图<br/>ledgerSummaryViewData:库存分类账-一览视图(月)<br/>ledgerSummaryViewDataByDay:库存分类账-一览视图(天)<br/>strandedInventoryUIData:无在售商品的亚马逊库存报告<br/>reservedInventoryData:预留库存报告<br/>fbaMYIAllInventoryData:管理亚马逊物流库存报告-已存档<br/>restockInventoryReport:补充库存<br/>afnInventoryDataByCountry:多国库存报告<br/>fbaFulfillmentInboundNoncomplianceData:FBA货件入库结果报告<br/>销量/流量：<br/>vat:亚马逊增值税交易报告<br/>salesAndTraffic:品牌分析报告<br/>amzFullfileldShipments:亚马逊配送货件<br/>amzAllOrders:所有订单<br/>fbaFulfillmentCustomerShipmentSalesData:已完成销售订单报告<br/>vatCalculation:亚马逊增值税计算报告<br/>付款：<br/>storage:月仓储费报告<br/>longtermStorage:长期仓储费报告<br/>reimbursements:赔偿数量报告<br/>fbaEstimatedFbaFeesTxtData:费用预览报告<br/>买家优惠：<br/>replacement:换货报告<br/>returns:退货报告<br/>移除数量：<br/>removalOrder:移除订单详情报告<br/>fbaFulfillmentRemovalShipmentDetailData:移除货件详情<br/>绩效：<br/>promotionPerformanceReport:秒杀活动报告<br/>couponPerformanceReport:优惠券报告<br/>品牌分析：<br/>brandAnalyticsRepeatPurchaseReportMonth:重复购买报告（月）<br/>brandAnalyticsSearchQueryPerformanceReportMonth:搜索查询表现报告（月）<br/>brandAnalyticsMarketBasketReportMonth:购物篮分析报告（月）<br/>brandAnalyticsMarketBasketReportDay:购物篮分析报告（天）
        startDate:
          type: string
          description: 请求时间-开始日期，时间格式应为：yyyy-MM-dd
        endDate:
          type: string
          description: 请求时间-结束日期，时间格式应为：yyyy-MM-dd
        reportOptions:
          type: array
          description: reportOptions
          items:
            $ref: '#/components/schemas/ReportOptionOpenVo'
        shopAsins:
          type: array
          description: 店铺asin列表，搜索查询表现报告（月）必传，数量限制在10个以内
          items:
            type: string
      title: ReportCenterAddParamOpenVo
      x-apifox-orders:
        - title
        - shopId
        - reportType
        - startDate
        - endDate
        - reportOptions
        - shopAsins
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ReportOptionOpenVo:
      type: object
      properties:
        optionKey:
          type: string
          description: 可选值KEY
        optionValue:
          type: string
          description: 可选值VALUE
      title: ReportOptionOpenVo
      x-apifox-orders:
        - optionKey
        - optionValue
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«IdData»:
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
          $ref: '#/components/schemas/IdData'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«IdData»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    IdData:
      type: object
      properties:
        id:
          type: string
          description: ID
      title: IdData
      x-apifox-orders:
        - id
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
