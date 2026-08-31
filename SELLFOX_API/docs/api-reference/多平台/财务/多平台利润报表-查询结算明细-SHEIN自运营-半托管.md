# 多平台利润报表-查询结算明细-SHEIN自运营/半托管

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/financial/aggReport/settlement/sheinHalfPage.json:
    post:
      summary: 多平台利润报表-查询结算明细-SHEIN自运营/半托管
      deprecated: false
      description: ''
      operationId: settlementSheinHalfPageUsingPOST
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
              $ref: '#/components/schemas/FinAggSheinHalfSettlementOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABFinAggSettlementSheinHalfOpenVO%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-426459619-run
components:
  schemas:
    FinAggSheinHalfSettlementOpenQo:
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
        dateQueryType:
          type: string
          description: '时间类型: 1-打款日期 2-订单签收日期'
          enum:
            - '1'
            - '2'
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
          description: >-
            账单类型: 1:订单收入; 2:订单退货; 3:订单调整; 4:仓库退货; 5:丢货补款; 6:订单异常补款; 8:订单异常扣款;
            10:银行打款验证; 11:订单状态修正; 12:订单履约服务费; 13:退货履约服务费; 14:订单履约服务费退还;
            15:履约服务费补款; 16:履约服务费扣款; 17:违规处罚补款; 18:违规处罚扣款; 19:平台激励补款; 20:平台激励扣款;
            21:税费补款; 22:税费扣款; 23:备货作业费; 24:退货冻结差额补款; 25:退货冻结差额扣款; 26:退货丢货补款;
            27:取消订单补款; 34:退货处理费; 35:GNRE税费补款; 36:GNRE税费扣款; 37:标准仓储费;
            38:超库龄附加仓储费; 39:交易申诉补款; 40:商家扣款单; 41:库存盘亏; 42:库存盘盈; 43:仓储费补款;
            44:仓储费扣款; 45:EPR补款; 46:EPR扣款; 47:SFS备货揽收费用; 48:海外备货运费补款;
            49:海外退供运费扣款; 50:仓储货物赔付补款; 51:仓储增值服务扣款; 52:商家合作押金补款; 53:定制化商家履约服务费补款;
            54:税费补贴; 55:税费补贴退回; 56:其他应补款; 57:其他应扣款; 58:线下欠款回收; 59:运费补贴;
            60:运费补贴退回; 61:退货运费补贴; 62:代收服务费; 63:违规处罚资金冻结; 64:违规撤销资金解冻;
            65:履约服务费附加费; 66:CA消费税补贴; 67:CA消费税补贴退回; 68:DIFAL增值税扣款; 69:客单正向成本调整;
            70:客单逆向成本调整; 71:客单结算; 72:退货结算; 73:支付手续费;
          items:
            type: string
            enum:
              - '1'
              - '2'
              - '3'
              - '4'
              - '5'
              - '6'
              - '8'
              - '10'
              - '11'
              - '12'
              - '13'
              - '14'
              - '15'
              - '16'
              - '17'
              - '18'
              - '19'
              - '20'
              - '21'
              - '22'
              - '23'
              - '24'
              - '25'
              - '26'
              - '27'
              - '34'
              - '35'
              - '36'
              - '37'
              - '38'
              - '39'
              - '40'
              - '41'
              - '42'
              - '43'
              - '44'
              - '45'
              - '46'
              - '47'
              - '48'
              - '49'
              - '50'
              - '51'
              - '52'
              - '53'
              - '54'
              - '55'
              - '56'
              - '57'
              - '58'
              - '59'
              - '60'
              - '61'
              - '62'
              - '63'
              - '64'
              - '65'
              - '66'
              - '67'
              - '68'
              - '69'
              - '70'
              - '71'
              - '72'
              - '73'
          examples:
            - - '1'
              - '2'
        incomeExpendTypeList:
          type: array
          description: '收支类型: 1-收入结算 2-扣款结算'
          items:
            type: integer
            format: int32
            enum:
              - 1
              - 2
          examples:
            - - 1
              - 2
        shopTypeList:
          type: array
          description: 模式, SELF:自运营 HALF:半托管
          items:
            type: string
            enum:
              - SELF
              - HALF
          examples:
            - HALF
        checkStatusList:
          type: array
          description: '对账单状态: 1:待生成付款 2:即将付款 3:已付款 4:付款异常'
          items:
            type: integer
            format: int32
            enum:
              - 1
              - 2
              - 3
              - 4
          examples:
            - 1
        searchType:
          type: string
          description: >-
            搜索字段, checkOrderNo:对账单号编码 orderId:订单号 bizOrderNo:业务单号
            platformSku:平台SKU msku:MSKU sku:SKU
          enum:
            - checkOrderNo
            - orderId
            - bizOrderNo
            - platformSku
            - msku
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
            可选:order_sign_time,commodity_price_sum,cost_price,seller_currency_promotion_price,settle_currency_promotion_price,shop_coupon_amount,service_amount,seller_real_tax,commission,commission_tax,performance_service_fee,stocking_opt_fee,return_hrr_unit_fee,receivable_total_amount,receivable_amount,sales_num,refund_num
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
      title: FinAggSheinHalfSettlementOpenQo
      x-apifox-orders:
        - shopIdList
        - dateQueryType
        - startDate
        - endDate
        - settlementStatusList
        - billTypeList
        - incomeExpendTypeList
        - shopTypeList
        - checkStatusList
        - searchType
        - searchMode
        - searchContents
        - orderBy
        - desc
        - pageNo
        - pageSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«FinAggSettlementSheinHalfOpenVO»:
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
          $ref: '#/components/schemas/FinAggSettlementSheinHalfOpenVO'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«FinAggSettlementSheinHalfOpenVO»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FinAggSettlementSheinHalfOpenVO:
      type: object
      properties:
        rows:
          type: array
          items:
            $ref: '#/components/schemas/FinAggSettlementSheinHalfPageOpenVO'
        totalPage:
          type: integer
          format: int32
          description: 总页数
        totalSize:
          type: integer
          format: int32
          description: 数据总条数
      title: FinAggSettlementSheinHalfOpenVO
      x-apifox-orders:
        - rows
        - totalPage
        - totalSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FinAggSettlementSheinHalfPageOpenVO:
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
        shopType:
          type: string
          description: 模式：SELF-自运营 HALF-半托管
        shopTypeName:
          type: string
          description: 模式名称
        orderId:
          type: string
          description: 订单号
        bizOrderNo:
          type: string
          description: 业务单号
        marketplaceCode:
          type: string
          description: 销售站点
        checkOrderNo:
          type: string
          description: 对账单编码
        checkStatus:
          type: integer
          format: int32
          description: 对账单状态,1、待生成付款；2、即将付款；3、已付款；4、付款异常
        checkStatusName:
          type: string
          description: 对账单状态名称
        platformSku:
          type: string
          description: 平台SKU
        sku:
          type: string
          description: SKU
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
        bizDayOrigin:
          type: string
          description: 打款日期
        orderSignTime:
          type: string
          description: 订单签收时间
        billType:
          type: integer
          format: int32
          description: 账单类型
        billTypeName:
          type: string
          description: 账单类型名称
        commodityPriceSum:
          type: number
          description: 商品价格汇总
        costPrice:
          type: number
          description: 商品供货价汇总
        sellerCurrencyPromotionPrice:
          type: number
          description: 活动优惠金额
        settleCurrencyPromotionPrice:
          type: number
          description: 活动提报金额
        shopCouponAmount:
          type: number
          description: 店铺优惠券金额
        serviceAmount:
          type: number
          description: 服务费
        sellerRealTax:
          type: number
          description: 欧洲增值税税金
        commission:
          type: number
          description: 佣金
        commissionTax:
          type: number
          description: 佣金消费税
        performanceServiceFee:
          type: number
          description: 履约服务费
        stockingOptFee:
          type: number
          description: 备货作业费
        returnHrrUnitFee:
          type: number
          description: 退货处理费
        receivableAmount:
          type: number
          description: 应收金额
        receivableTotalAmount:
          type: number
          description: 应收总金额
      title: FinAggSettlementSheinHalfPageOpenVO
      x-apifox-orders:
        - currency
        - shopId
        - shopName
        - shopType
        - shopTypeName
        - orderId
        - bizOrderNo
        - marketplaceCode
        - checkOrderNo
        - checkStatus
        - checkStatusName
        - platformSku
        - sku
        - msku
        - salesNum
        - refundNum
        - bizDayOrigin
        - orderSignTime
        - billType
        - billTypeName
        - commodityPriceSum
        - costPrice
        - sellerCurrencyPromotionPrice
        - settleCurrencyPromotionPrice
        - shopCouponAmount
        - serviceAmount
        - sellerRealTax
        - commission
        - commissionTax
        - performanceServiceFee
        - stockingOptFee
        - returnHrrUnitFee
        - receivableAmount
        - receivableTotalAmount
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
