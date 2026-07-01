# FBM退货报告查询

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/order/api/report/fbm/return/order/pageList.json:
    post:
      summary: FBM退货报告查询
      deprecated: false
      description: ''
      operationId: pageListUsingPOST_5
      tags:
        - 销售/退货报告
        - 销售
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
              $ref: '#/components/schemas/FbmReturnOrderOpenQo'
            example: ''
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABFbmReturnOrderOpenVo%C2%BB%C2%BB
          headers: {}
          x-apifox-name: OK
        '201':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: Created
        '401':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: Unauthorized
        '403':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: Forbidden
        '404':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: Not Found
      security: []
      x-apifox-folder: 销售/退货报告
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-116412070-run
components:
  schemas:
    FbmReturnOrderOpenQo:
      type: object
      properties:
        pageSize:
          type: string
          description: 每页大小
        pageNo:
          type: string
          description: 第几页
        marketplaceIdList:
          type: array
          description: 站点
          items:
            type: string
        shopIdList:
          type: array
          description: 店铺
          items:
            type: string
        status:
          type: array
          description: >-
            退货状态,可选值:AuthorizationRequried,Approved,PendingApproval,PendingActions,Completed,Closed,WithA-to-ZGuranteeClaim
          items:
            type: string
        orderStartDate:
          type: string
          description: 订购开始日期
        orderEndDate:
          type: string
          description: 订购结束日期
        returnStartDate:
          type: string
          description: 退货开始日期
        returnEndDate:
          type: string
          description: 退货结束日期
        primeOrder:
          type: string
          description: 'Prime会员订单,默认false: false;true'
        supportClaim:
          type: string
          description: 'A-to-Z索赔,默认false: false;true'
        searchType:
          type: string
          description: >-
            搜索类型,订单号:orderId;亚马逊RMA单号:amazonRmaId;运单号:trackingId;ASIN:asin,MSKU:msku,SKU:sku,品名:commodityName,备注:remark
        searchContent:
          type: array
          description: 搜索值
          items:
            type: string
      title: FbmReturnOrderOpenQo
      x-apifox-orders:
        - pageSize
        - pageNo
        - marketplaceIdList
        - shopIdList
        - status
        - orderStartDate
        - orderEndDate
        - returnStartDate
        - returnEndDate
        - primeOrder
        - supportClaim
        - searchType
        - searchContent
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«Page«FbmReturnOrderOpenVo»»:
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
          $ref: '#/components/schemas/Page%C2%ABFbmReturnOrderOpenVo%C2%BB'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«FbmReturnOrderOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    Page«FbmReturnOrderOpenVo»:
      type: object
      properties:
        pageNo:
          type: integer
          format: int32
          description: 页码
        pageSize:
          type: integer
          format: int32
          description: 每页条数
        totalPage:
          type: integer
          format: int32
          description: 总页数
        totalSize:
          type: integer
          format: int32
          description: 总条数
        rows:
          type: array
          description: 当前页数据
          items:
            $ref: '#/components/schemas/FbmReturnOrderOpenVo'
      title: Page«FbmReturnOrderOpenVo»
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FbmReturnOrderOpenVo:
      type: object
      properties:
        id:
          type: string
          description: id
        sellerId:
          type: string
          description: sellerId
        shopId:
          type: string
          description: 店铺ID
        shopName:
          type: string
          description: 店铺名称
        marketplaceId:
          type: string
          description: 站点ID
        marketplaceName:
          type: string
          description: 站点名称
        orderId:
          type: string
          description: 订单ID
        orderDate:
          type: string
          description: 订购日期
        orderQuantity:
          type: string
          description: 销量
        orderAmount:
          type: string
          description: 销售收益
        currency:
          type: string
          description: 币种
        commodityId:
          type: string
          description: 商品ID
        commoditySku:
          type: string
          description: SKU
        commodityName:
          type: string
          description: 品名
        asin:
          type: string
          description: asin
        msku:
          type: string
          description: msku
        title:
          type: string
          description: 产品标题
        remark:
          type: string
          description: 备注
        returnRequestDate:
          type: string
          description: 退款请求日期
        returnQuantity:
          type: string
          description: 退货量
        refundedAmount:
          type: string
          description: 退款金额
        returnRequestStatus:
          type: string
          description: 退款请求状态
        returnType:
          type: string
          description: 退货类型
        returnReason:
          type: string
          description: 退货原因
        returnDeliveryDate:
          type: string
          description: 退货送达日期
        diffDay:
          type: string
          description: 售后间隔天数
        labelType:
          type: string
          description: 标签类型
        labelToBePaidBy:
          type: string
          description: 标签支付方
        labelCost:
          type: string
          description: 标签费用
        returnCarrier:
          type: string
          description: 承运商
        trackingId:
          type: string
          description: 运单号
        inPolicy:
          type: string
          description: 符合政策
        resolution:
          type: string
          description: 解决方法
        invoiceNumber:
          type: string
          description: 发票号码
        amazonRmaId:
          type: string
          description: 亚马逊退货跟踪号
        merchantRmaId:
          type: string
          description: 卖家退货跟踪号
        safeActionReason:
          type: string
          description: Safe-T索赔原因
        safeClaimId:
          type: string
          description: Safe-T索赔单号
        safeClaimState:
          type: string
          description: Safe-T索赔状态
        safeClaimCreationTime:
          type: string
          description: Safe-T索赔时间
        safeClaimReimbursementAmount:
          type: string
          description: Safe-T索赔金额
        category:
          type: string
          description: 分类
        atozClaim:
          type: string
          description: A-to-Z索赔
        isPrime:
          type: string
          description: Prime订单
        itemName:
          type: string
          description: 报告产品
        mainImage:
          type: string
          description: 主图
        productId:
          type: string
          description: 产品ID
        productName:
          type: string
          description: 产品名称
      title: FbmReturnOrderOpenVo
      x-apifox-orders:
        - id
        - sellerId
        - shopId
        - shopName
        - marketplaceId
        - marketplaceName
        - orderId
        - orderDate
        - orderQuantity
        - orderAmount
        - currency
        - commodityId
        - commoditySku
        - commodityName
        - asin
        - msku
        - title
        - remark
        - returnRequestDate
        - returnQuantity
        - refundedAmount
        - returnRequestStatus
        - returnType
        - returnReason
        - returnDeliveryDate
        - diffDay
        - labelType
        - labelToBePaidBy
        - labelCost
        - returnCarrier
        - trackingId
        - inPolicy
        - resolution
        - invoiceNumber
        - amazonRmaId
        - merchantRmaId
        - safeActionReason
        - safeClaimId
        - safeClaimState
        - safeClaimCreationTime
        - safeClaimReimbursementAmount
        - category
        - atozClaim
        - isPrime
        - itemName
        - mainImage
        - productId
        - productName
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
