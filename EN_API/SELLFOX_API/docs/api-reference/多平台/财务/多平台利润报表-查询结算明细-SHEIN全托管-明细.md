# 多平台利润报表-查询结算明细-SHEIN全托管-明细

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/financial/aggReport/settlement/sheinAgent/detailPage.json:
    post:
      summary: 多平台利润报表-查询结算明细-SHEIN全托管-明细
      deprecated: false
      description: ''
      operationId: settlementSheinAgentDetailPageUsingPOST
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
              $ref: '#/components/schemas/FinAggSheinAgentSettlementDetailOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABFinAggSettlementSheinAgenDetailOpenVO%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-426459617-run
components:
  schemas:
    FinAggSheinAgentSettlementDetailOpenQo:
      type: object
      required:
        - dateQueryType
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
        marketplaceCodes:
          type: array
          description: 站点
          items:
            type: string
          examples:
            - - '1'
              - '2'
              - '3'
        dateQueryType:
          type: string
          description: '时间类型: 1-实际结算日期 2-预计结算日期 3-报账单生成日期 4-添加时间'
          enum:
            - '1'
            - '2'
            - '3'
            - '4'
          examples:
            - 1
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
        settlementStatusList:
          type: array
          description: 结算状态, 1:待确认 2:待结算 3:已结算
          items:
            type: integer
            format: int32
            enum:
              - 1
              - 2
              - 3
          examples:
            - - 1
              - 2
              - 3
        billTypeList:
          type: array
          description: 账单类型, 1:销售款 2:补扣款
          items:
            type: string
            enum:
              - '1'
              - '2'
          examples:
            - - '1'
              - '2'
        incomeExpendTypeList:
          type: array
          description: 收支类型, 1:收入结算 2:扣款结算
          items:
            type: integer
            format: int32
            enum:
              - 1
              - 2
          examples:
            - - 1
              - 2
        idSearchType:
          type: string
          description: >-
            搜索字段(单号类), reportOrderNo:报账单号 bizOrderNo:业务单号
            supplementaryDeductionNo:补扣款单号
          enum:
            - reportOrderNo
            - bizOrderNo
            - supplementaryDeductionNo
          examples:
            - reportOrderNo
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
          description: 搜索字段, msku:MSKU skc:SKC platformSku:平台SKU sku:SKU
          enum:
            - msku
            - skc
            - platformSku
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
            排序字段, 默认:biz_day_origin,
            可选:biz_day_origin,order_sign_time,commodity_price_sum,cost_price,seller_currency_promotion_price,settle_currency_promotion_price,shop_coupon_amount,service_amount,seller_real_tax,commission,commission_tax,performance_service_fee,stocking_opt_fee,return_hrr_unit_fee,receivable_total_amount,receivable_amount,sales_num,refund_num
          enum:
            - biz_day_origin
            - order_sign_time
            - commodity_price_sum
            - cost_price
            - seller_currency_promotion_price
            - settle_currency_promotion_price
            - shop_coupon_amount
            - service_amount
            - seller_real_tax
            - commission
            - commission_tax
            - performance_service_fee
            - stocking_opt_fee
            - return_hrr_unit_fee
            - receivable_total_amount
            - receivable_amount
            - sales_num
            - refund_num
          examples:
            - biz_day_origin
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
      title: FinAggSheinAgentSettlementDetailOpenQo
      x-apifox-orders:
        - shopIdList
        - marketplaceCodes
        - dateQueryType
        - startDate
        - endDate
        - settlementStatusList
        - billTypeList
        - incomeExpendTypeList
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
    OpenResult«FinAggSettlementSheinAgenDetailOpenVO»:
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
          $ref: '#/components/schemas/FinAggSettlementSheinAgenDetailOpenVO'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«FinAggSettlementSheinAgenDetailOpenVO»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FinAggSettlementSheinAgenDetailOpenVO:
      type: object
      properties:
        rows:
          type: array
          items:
            $ref: '#/components/schemas/FinAggSettlementSheinAgenDetailPageOpenVO'
        totalPage:
          type: integer
          format: int32
          description: 总页数
        totalSize:
          type: integer
          format: int32
          description: 数据总条数
      title: FinAggSettlementSheinAgenDetailOpenVO
      x-apifox-orders:
        - rows
        - totalPage
        - totalSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FinAggSettlementSheinAgenDetailPageOpenVO:
      type: object
      properties:
        currency:
          type: string
          description: 币种
        shopId:
          type: integer
          format: int64
          description: 店铺ID
        shopName:
          type: string
          description: 店铺名称
        reportOrderTime:
          type: string
          description: 报账单生成日期
        reportOrderNo:
          type: string
          description: 报账单号
        estimatePayTime:
          type: string
          description: 预计结算日期
        completedPayTime:
          type: string
          description: 实际结算日期
        settlementStatus:
          type: integer
          format: int32
          description: 结算状态，1：待确认 2：待结算 3：已结算
        settlementStatusName:
          type: string
          description: 结算状态名称
        addTime:
          type: string
          description: 添加时间
        billType:
          type: string
          description: 账单类型:1-销售款 2-补扣款
        billTypeName:
          type: string
          description: 账单类型名称
        incomeExpendType:
          type: integer
          format: int32
          description: 收支类型:1-收入结算 2-扣款结算
        incomeExpendTypeName:
          type: string
          description: 收支类型名称
        paymentCategory:
          type: string
          description: 款项分类
        skc:
          type: string
          description: SKC
        platformSku:
          type: string
          description: 平台SKU
        sku:
          type: string
          description: SKU
        msku:
          type: string
          description: MSKU
        unitPrice:
          type: number
          description: 单价
        goodsCount:
          type: integer
          format: int32
          description: 数量
        amount:
          type: number
          description: 金额
        bizOrderNo:
          type: string
          description: 业务单号
        supplementaryDeductionNo:
          type: string
          description: 补扣款单号
      title: FinAggSettlementSheinAgenDetailPageOpenVO
      x-apifox-orders:
        - currency
        - shopId
        - shopName
        - reportOrderTime
        - reportOrderNo
        - estimatePayTime
        - completedPayTime
        - settlementStatus
        - settlementStatusName
        - addTime
        - billType
        - billTypeName
        - incomeExpendType
        - incomeExpendTypeName
        - paymentCategory
        - skc
        - platformSku
        - sku
        - msku
        - unitPrice
        - goodsCount
        - amount
        - bizOrderNo
        - supplementaryDeductionNo
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
