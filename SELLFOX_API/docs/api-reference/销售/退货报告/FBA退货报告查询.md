# FBA退货报告查询

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/order/api/report/fbaReturn/pageList.json:
    post:
      summary: FBA退货报告查询
      deprecated: false
      description: ''
      operationId: apiPageListUsingPOST_1
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
              $ref: '#/components/schemas/ReportParamOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABReportFbaReturnsOpenVo%C2%BB%C2%BB
          headers: {}
          x-apifox-name: OK
        '201':
          description: Created
          headers: {}
          x-apifox-name: Created
        '401':
          description: Unauthorized
          headers: {}
          x-apifox-name: Unauthorized
        '403':
          description: Forbidden
          headers: {}
          x-apifox-name: Forbidden
        '404':
          description: Not Found
          headers: {}
          x-apifox-name: Not Found
      security: []
      x-order: '6'
      x-apifox-folder: 销售/退货报告
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-116412069-run
components:
  schemas:
    ReportParamOpenQo:
      type: object
      properties:
        pageNo:
          type: string
          description: 第几页
        pageSize:
          type: string
          description: 每页大小
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
        detailedDisposition:
          type: array
          description: >-
            库存属性,可选值:可售:SELLABLE;残损:DAMAGED;买家损坏:CUSTOMER_DAMAGED;不可售:DEFECTIVE;承运人损坏:CARRIER_DAMAGED;过期:EXPIRED;
          items:
            type: string
        reason:
          type: array
          description: >-
            退货原因,可选值:退货选项不可用:OTHER;订购了错误的商品:ORDERED_WRONG_ITEM;发现了更优惠的价格:FOUND_BETTER_PRICE;没有原因:NO_REASON_GIVEN;质量未达到期望:QUALITY_UNACCEPTABLE;不兼容:NOT_COMPATIBLE;仓库损坏:DAMAGED_BY_FC;超时未送达:MISSED_ESTIMATED_DELIVERY;配件缺失:MISSING_PARTS;承运商损坏:DAMAGED_BY_CARRIER;派送错误商品:SWITCHEROO;有瑕疵:DEFECTIVE;包裹中包含其他商品:EXTRA_ITEM;不想要的商品:UNWANTED_ITEM;商品运送时出现瑕疵:WARRANTY;未授权的购买:UNAUTHORIZED_PURCHASE;无法配送：地址不详:UNDELIVERABLE_INSUFFICIENT_ADDRESS;无法配送：多次派送无人收件:UNDELIVERABLE_FAILED_DELIVERY_ATTEMPTS;无法配送：拒收:UNDELIVERABLE_REFUSED;无法配送：未知原因:UNDELIVERABLE_UNKNOWN;无法配送：无人认领:UNDELIVERABLE_UNCLAIMED;无法配送：缺失标签:UNDELIVERABLE_MISSING_LABEL;无法配送：承运商未处理:UNDELIVERABLE_CARRIER_MISS_SORTED;服装：商品尺码太小:APPAREL_TOO_SMALL;服装：商品尺码太大:APPAREL_TOO_LARGE;服装：不喜欢服装款式:APPAREL_STYLE;订购错误的款式/尺码/颜色:MISORDERED;与描述不一致:NOT_AS_DESCRIBED;不喜欢的颜色:DID_NOT_LIKE_COLOR;不喜欢的布料:DID_NOT_LIKE_FABRIC;没有收到:NEVER_ARRIVED;过度安装:EXCESSIVE_INSTALLATION;部分不兼容:PART_NOT_COMPATIBLE;珠宝首饰：太小/短:JEWELRY_TOO_SMALL;珠宝首饰：太大/长:JEWELRY_TOO_LARGE;珠宝首饰：电池没电:JEWELRY_BATTERY;珠宝首饰：缺少使用手册/质保:JEWELRY_NO_DOCS;珠宝首饰：挂钩损坏:JEWELRY_BAD_CLASP;珠宝首饰：宝石松脱:JEWELRY_LOOSE_STONE;珠宝首饰：缺少证书:JEWELRY_NO_CERT;珠宝首饰：暗淡无光:JEWELRY_TARNISHED;
          items:
            type: string
        status:
          type: array
          description: >-
            退货状态,可选值:商品已退回库存:Unit returned to
            inventory;已赔偿:Reimbursed;已成功重新包装:Repackaged
            Successfully;即将处置:IMMEDIATE_DISPOSAL;
          items:
            type: string
        returnStartDate:
          type: string
          description: 退货时间开始时间,格式yyyy-MM-dd
        returnEndDate:
          type: string
          description: 退货时间结束时间,格式yyyy-MM-dd
        returnSiteStartDate:
          type: string
          description: 退货站点时间开始时间,格式yyyy-MM-dd
        returnSiteEndDate:
          type: string
          description: 退货站点时间结束时间,格式yyyy-MM-dd
        orderStartDate:
          type: string
          description: 订购时间开始时间,格式yyyy-MM-dd
        orderEndDate:
          type: string
          description: 订购时间结束时间,格式yyyy-MM-dd
        checkUnSet:
          type: string
          description: 未设置店铺的订单,默认为0,1:过滤,0:不过滤
        searchType:
          type: string
          description: >-
            搜索类型,订单号:orderId;ASIN:asin;MSKU:msku;标题:title;SKU:sku;品名:commodityName;备注:remark;LPN编号:licensePlateNumber;备注:remark;
        searchContent:
          type: array
          description: 搜索值
          items:
            type: string
      title: ReportParamOpenQo
      x-apifox-orders:
        - pageNo
        - pageSize
        - marketplaceIdList
        - shopIdList
        - detailedDisposition
        - reason
        - status
        - returnStartDate
        - returnEndDate
        - returnSiteStartDate
        - returnSiteEndDate
        - orderStartDate
        - orderEndDate
        - checkUnSet
        - searchType
        - searchContent
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«Page«ReportFbaReturnsOpenVo»»:
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
          $ref: '#/components/schemas/Page%C2%ABReportFbaReturnsOpenVo%C2%BB'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«ReportFbaReturnsOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    Page«ReportFbaReturnsOpenVo»:
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
            $ref: '#/components/schemas/ReportFbaReturnsOpenVo'
      title: Page«ReportFbaReturnsOpenVo»
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ReportFbaReturnsOpenVo:
      type: object
      properties:
        id:
          type: string
          description: id
        sellerId:
          type: string
          description: 亚马逊卖家编号
        shopId:
          type: string
          description: shopId
        shopName:
          type: string
          description: 店铺名称
        marketplaceId:
          type: string
          description: 站点id
        marketplaceName:
          type: string
          description: 站点名称
        region:
          type: string
          description: 大区，na,eu,fe
        convReturnDate:
          type: string
          description: 退货时间
        returnSiteTime:
          type: string
          description: 退货站点时间
        orderDate:
          type: string
          description: 订购时间
        msku:
          type: string
          description: msku
        asin:
          type: string
          description: ASIN
        fnsku:
          type: string
          description: FNSKU
        productName:
          type: string
          description: 产品名称
        orderId:
          type: string
          description: 订单ID
        quantity:
          type: string
          description: 退货量
        fulfillmentCenterId:
          type: string
          description: 发货仓库编号
        detailedDisposition:
          type: string
          description: 库存属性
        detailedDispositionStr:
          type: string
          description: 库存属性中文描述
        reason:
          type: string
          description: 退货原因
        reasonStr:
          type: string
          description: 退货原因中文描述
        status:
          type: string
          description: 退货状态
        statusStr:
          type: string
          description: 退货状态中文描述
        licensePlateNumber:
          type: string
          description: LPN
        customerComments:
          type: string
          description: 客户意见
        remark:
          type: string
          description: 备注
        commoditySku:
          type: string
          description: 商品SKU
        commodityId:
          type: string
          description: 商品ID
        commodityName:
          type: string
          description: 品名
        mainImage:
          type: string
          description: 主图
        title:
          type: string
          description: 标题
      title: ReportFbaReturnsOpenVo
      x-apifox-orders:
        - id
        - sellerId
        - shopId
        - shopName
        - marketplaceId
        - marketplaceName
        - region
        - convReturnDate
        - returnSiteTime
        - orderDate
        - msku
        - asin
        - fnsku
        - productName
        - orderId
        - quantity
        - fulfillmentCenterId
        - detailedDisposition
        - detailedDispositionStr
        - reason
        - reasonStr
        - status
        - statusStr
        - licensePlateNumber
        - customerComments
        - remark
        - commoditySku
        - commodityId
        - commodityName
        - mainImage
        - title
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
