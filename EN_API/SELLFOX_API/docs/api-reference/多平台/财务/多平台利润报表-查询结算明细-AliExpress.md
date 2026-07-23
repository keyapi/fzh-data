# 多平台利润报表-查询结算明细-AliExpress

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/financial/aggReport/settlement/aliExpressPage.json:
    post:
      summary: 多平台利润报表-查询结算明细-AliExpress
      deprecated: false
      description: ''
      operationId: settlementAliExpressPageUsingPOST
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
              $ref: '#/components/schemas/FinAggAliexpressSettlementOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABFinAggSettlementAliexpressOpenVO%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-426459614-run
components:
  schemas:
    FinAggAliexpressSettlementOpenQo:
      type: object
      required:
        - startDate
        - endDate
      properties:
        shopIdList:
          type: array
          description: 店铺ID
          items:
            type: integer
            format: int32
          examples:
            - - 1
              - 2
              - 3
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
        searchType:
          type: string
          description: 搜索字段,orderId:订单号
          enum:
            - orderId
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
          description: 排序字段，receipt_flow_time,receipt_flow_amount
          enum:
            - receipt_flow_time
            - receipt_flow_amount
          examples:
            - receipt_flow_time
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
      title: FinAggAliexpressSettlementOpenQo
      x-apifox-orders:
        - shopIdList
        - startDate
        - endDate
        - currency
        - searchType
        - searchMode
        - searchContents
        - orderBy
        - desc
        - pageNo
        - pageSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«FinAggSettlementAliexpressOpenVO»:
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
          $ref: '#/components/schemas/FinAggSettlementAliexpressOpenVO'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«FinAggSettlementAliexpressOpenVO»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FinAggSettlementAliexpressOpenVO:
      type: object
      properties:
        rows:
          type: array
          items:
            $ref: '#/components/schemas/FinAggSettlementAliexpressPageOpenVO'
        totalPage:
          type: integer
          format: int32
          description: 总页数
        totalSize:
          type: integer
          format: int32
          description: 数据总条数
      title: FinAggSettlementAliexpressOpenVO
      x-apifox-orders:
        - rows
        - totalPage
        - totalSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FinAggSettlementAliexpressPageOpenVO:
      type: object
      properties:
        receiptFlowTime:
          type: string
          description: 结算时间
        shopId:
          type: string
          description: 店铺ID
        shopName:
          type: string
          description: 店铺
        receiptFlowName:
          type: string
          description: 费用项
        receiptFlowAmount:
          type: number
          description: 变动金额
        tradeOrderId:
          type: string
          description: 订单号
        receiptFlowRemark:
          type: string
          description: 备注
        fromIdentityType:
          type: string
          description: 支出账户
        toIdentityType:
          type: string
          description: 收入账户
        receiptFlowId:
          type: string
          description: 平台流水单号
        currency:
          type: string
          description: 币种
      title: FinAggSettlementAliexpressPageOpenVO
      x-apifox-orders:
        - receiptFlowTime
        - shopId
        - shopName
        - receiptFlowName
        - receiptFlowAmount
        - tradeOrderId
        - receiptFlowRemark
        - fromIdentityType
        - toIdentityType
        - receiptFlowId
        - currency
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
