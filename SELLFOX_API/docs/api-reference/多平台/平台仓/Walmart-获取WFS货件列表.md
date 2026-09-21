# Walmart-获取WFS货件列表

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /openapi/psi/walmart/wfsShipment/pageList.json:
    post:
      summary: Walmart-获取WFS货件列表
      deprecated: false
      description: ''
      operationId: pageListUsingPOST_28
      tags:
        - 多平台/平台仓
        - WFS货件
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
              $ref: '#/components/schemas/WfsShipmentPageOpenQO'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/WFS%E8%B4%A7%E4%BB%B6%E5%88%86%E9%A1%B5%E8%BF%94%E5%9B%9E
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
      x-apifox-folder: 多平台/平台仓
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-510029214-run
components:
  schemas:
    WfsShipmentPageOpenQO:
      type: object
      required:
        - pageNo
        - pageSize
      properties:
        shipmentIdList:
          type: array
          description: WFS货件号，精确搜索
          items:
            type: string
        shopId:
          type: integer
          format: int64
          description: 店铺ID
        startDate:
          type: string
          description: 创建时间开始，yyyy-MM-dd
          examples:
            - '2026-01-01'
        endDate:
          type: string
          description: 创建时间结束，yyyy-MM-dd
          examples:
            - '2026-01-01'
        pageNo:
          type: string
          description: 第几页
        pageSize:
          type: string
          description: 每页大小
      title: WfsShipmentPageOpenQO
      x-apifox-orders:
        - shipmentIdList
        - shopId
        - startDate
        - endDate
        - pageNo
        - pageSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    WFS货件分页返回:
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
            $ref: '#/components/schemas/WfsShipmentOpenVO'
      title: WFS货件分页返回
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    WfsShipmentOpenVO:
      type: object
      properties:
        id:
          type: integer
          format: int64
          description: 主键ID
        puid:
          type: integer
          format: int64
          description: 主用户ID
        shipmentId:
          type: string
          description: WFS货件ID
        shopAuthId:
          type: integer
          format: int64
          description: 店铺授权ID
        shopAuthName:
          type: string
          description: 店铺名称
        source:
          type: integer
          format: int32
          description: 来源：1-Sellfox系统，2-Walmart平台
        expectedDeliveryDate:
          type: string
          description: 预计到货时间
        inBoundOrderId:
          type: string
          description: 发货单号
        carrier:
          type: string
          description: 物流商
        remark:
          type: string
          description: 备注
        status:
          type: integer
          format: int32
          description: 状态
        returnPersonName:
          type: string
          description: 退货人名称
        shipCity:
          type: string
          description: 配送城市
        shipState:
          type: string
          description: 配送州/省
        shipCountryCode:
          type: string
          description: 配送国家码
        shipCountryName:
          type: string
          description: 配送国家名称
        shipPostalCode:
          type: string
          description: 配送邮编
        firstShipAddress:
          type: string
          description: 配送地址1
        secondShipAddress:
          type: string
          description: 配送地址2
        returnCity:
          type: string
          description: 退货城市
        returnState:
          type: string
          description: 退货州/省
        returnCountryCode:
          type: string
          description: 退货国家码
        returnCountryName:
          type: string
          description: 退货国家名称
        returnPostalCode:
          type: string
          description: 退货邮编
        firstReturnAddress:
          type: string
          description: 退货地址1
        secondReturnAddress:
          type: string
          description: 退货地址2
        isGenerateDelivery:
          type: integer
          format: int32
          description: 是否生成发货单：0-未生成，1-已生成，2-无需生成
        createId:
          type: integer
          format: int64
          description: 创建人ID
        createName:
          type: string
          description: 创建人
        createTime:
          type: string
          description: 创建时间
        updateId:
          type: integer
          format: int64
          description: 更新人ID
        updateTime:
          type: string
          description: 更新时间
        wfsShipmentItemVOList:
          type: array
          description: WFS货件商品明细
          items:
            $ref: '#/components/schemas/WfsShipmentItemOpenVO'
        wfsShipmentTrackingVOList:
          type: array
          description: 物流跟踪信息
          items:
            $ref: '#/components/schemas/WfsShipmentTrackingOpenVO'
        platformShippingSnVOList:
          type: array
          description: 平台发货单信息
          items:
            $ref: '#/components/schemas/PlatformShippingSnOpenVO'
      title: WfsShipmentOpenVO
      x-apifox-orders:
        - id
        - puid
        - shipmentId
        - shopAuthId
        - shopAuthName
        - source
        - expectedDeliveryDate
        - inBoundOrderId
        - carrier
        - remark
        - status
        - returnPersonName
        - shipCity
        - shipState
        - shipCountryCode
        - shipCountryName
        - shipPostalCode
        - firstShipAddress
        - secondShipAddress
        - returnCity
        - returnState
        - returnCountryCode
        - returnCountryName
        - returnPostalCode
        - firstReturnAddress
        - secondReturnAddress
        - isGenerateDelivery
        - createId
        - createName
        - createTime
        - updateId
        - updateTime
        - wfsShipmentItemVOList
        - wfsShipmentTrackingVOList
        - platformShippingSnVOList
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    PlatformShippingSnOpenVO:
      type: object
      properties:
        platformShippingOrderId:
          type: integer
          format: int64
          description: 平台发货单ID
        shipSn:
          type: string
          description: 发货单号
      title: PlatformShippingSnOpenVO
      x-apifox-orders:
        - platformShippingOrderId
        - shipSn
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    WfsShipmentTrackingOpenVO:
      type: object
      properties:
        id:
          type: integer
          format: int64
          description: 主键ID
        wfsShipmentId:
          type: integer
          format: int64
          description: WFS货件信息表ID
        shipmentId:
          type: string
          description: WFS货件ID
        logisticsCompanyName:
          type: string
          description: 物流商名称
        trackingNo:
          type: string
          description: 运单号
      title: WfsShipmentTrackingOpenVO
      x-apifox-orders:
        - id
        - wfsShipmentId
        - shipmentId
        - logisticsCompanyName
        - trackingNo
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    WfsShipmentItemOpenVO:
      type: object
      properties:
        id:
          type: integer
          format: int64
          description: 明细主键ID
        wfsShipmentId:
          type: integer
          format: int64
          description: WFS货件信息表ID
        shipmentId:
          type: string
          description: WFS货件ID
        wfsProductId:
          type: integer
          format: int64
          description: WFS在线产品ID
        shopAuthId:
          type: integer
          format: int64
          description: 店铺授权ID
        shopAuthName:
          type: string
          description: 店铺名称
        sellerSku:
          type: string
          description: MSKU
        commodityName:
          type: string
          description: 商品名称
        commodityId:
          type: integer
          format: int64
          description: 商品ID
        commoditySku:
          type: string
          description: 商品SKU
        commodityType:
          type: integer
          format: int32
          description: 商品类型
        gtin:
          type: string
          description: GTIN码
        shipmentQty:
          type: integer
          format: int32
          description: 申报量
        deliveryQty:
          type: integer
          format: int32
          description: 发货量
        receivedQty:
          type: integer
          format: int32
          description: 签收量
        shipmentDeliveryQty:
          type: integer
          format: int32
          description: 申发差异，申报量 - 发货量
        shipmentReceivedQty:
          type: integer
          format: int32
          description: 申收差异，申报量 - 签收量
        packingType:
          type: integer
          format: int32
          description: 装箱类型：1-Case Pack，2-Individual
        boxQty:
          type: integer
          format: int32
          description: 每箱数量
        productId:
          type: string
          description: Walmart平台产品ID
        imgUrl:
          type: string
          description: 图片URL
      title: WfsShipmentItemOpenVO
      x-apifox-orders:
        - id
        - wfsShipmentId
        - shipmentId
        - wfsProductId
        - shopAuthId
        - shopAuthName
        - sellerSku
        - commodityName
        - commodityId
        - commoditySku
        - commodityType
        - gtin
        - shipmentQty
        - deliveryQty
        - receivedQty
        - shipmentDeliveryQty
        - shipmentReceivedQty
        - packingType
        - boxQty
        - productId
        - imgUrl
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
