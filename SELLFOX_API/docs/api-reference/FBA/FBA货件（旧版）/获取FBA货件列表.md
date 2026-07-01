# 获取FBA货件列表

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/fba/shipmentPageList.json:
    post:
      summary: 获取FBA货件列表
      deprecated: false
      description: ''
      operationId: shipmentPageListUsingPOST
      tags:
        - FBA/FBA货件（旧版）
        - FBA货件
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
              $ref: '#/components/schemas/ShipmentSearchOpenParam'
            example: ''
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABShipmentOpenVo%C2%BB%C2%BB
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
      x-apifox-folder: FBA/FBA货件（旧版）
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-51516609-run
components:
  schemas:
    ShipmentSearchOpenParam:
      type: object
      required:
        - createTimeStart
        - createTimeEnd
      properties:
        shopIdList:
          type: array
          description: 店铺
          items:
            type: string
        marketplaceIdList:
          type: array
          description: 站点
          items:
            type: string
        shipmentStatusList:
          type: array
          description: 货件状态
          items:
            type: string
        amazonShipmentIdList:
          type: array
          description: 货件编号
          items:
            type: string
        createTimeStart:
          type: string
          description: 创建时间开始于，yyyy-MM-dd hh:mm:ss
          examples:
            - '2025-01-01 00:00:00'
        createTimeEnd:
          type: string
          description: 创建时间结束于，yyyy-MM-dd hh:mm:ss
          examples:
            - '2025-01-01 23:59:59'
        cartonFeedStatus:
          type: array
          description: 货件装箱状态：0待装箱 1装箱中 2失败 3成功 4失效
          items:
            type: string
        pageNo:
          type: string
          description: 第几页
        pageSize:
          type: string
          description: 每页大小
      title: ShipmentSearchOpenParam
      x-apifox-orders:
        - shopIdList
        - marketplaceIdList
        - shipmentStatusList
        - amazonShipmentIdList
        - createTimeStart
        - createTimeEnd
        - cartonFeedStatus
        - pageNo
        - pageSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«Page«ShipmentOpenVo»»:
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
          $ref: '#/components/schemas/Page%C2%ABShipmentOpenVo%C2%BB'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«ShipmentOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    Page«ShipmentOpenVo»:
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
            $ref: '#/components/schemas/ShipmentOpenVo'
      title: Page«ShipmentOpenVo»
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ShipmentOpenVo:
      type: object
      properties:
        id:
          type: string
          description: id
        shopId:
          type: string
          description: shopId
        marketplaceId:
          type: string
          description: marketplaceId
        amazonShipmentId:
          type: string
          description: amazonShipmentId
        name:
          type: string
          description: name
        fromAddress: &ref_0
          $ref: '#/components/schemas/AmznFBAAddressOpenVo'
        fulfillmentCenterId:
          type: string
          description: fulfillmentCenterId
        toAddress: *ref_0
        labelPrepType:
          type: string
          description: 产品标签处理类型
        labelPrepPreference:
          type: string
          description: 产品标签处理方
        areCasesRequired:
          type: string
          description: areCasesRequired
        skuKinds:
          type: string
          description: sku种类
        shipmentStatus:
          type: string
          description: >-
            货件状态,可选值：WORKING/READY_TO_SHIP/SHIPPED/IN_TRANSIT/DELIVERED/CHECKED_IN/RECEIVING/CLOSED/CANCELLED/DELETED
        transitStatus:
          type: string
          description: 货件是否算在途（1：计算在途，0：不计算在途）
        transitStatusForShipOrder:
          type: string
          description: 标记发货单模式时，货件是否算在途（1：计算在途，0：不计算在途）
        uploadTrack:
          type: string
          description: 是否已经上传运单号0:不是，1:是'
        shipmentType:
          type: string
          description: 货件类型
        isPartnered:
          type: string
          description: 是否亚马逊合作承运人
        carrierName:
          type: string
          description: 承运人
        markShipped:
          type: string
          description: 是否标记发货，1:是'
        cartonType:
          type: string
          description: 装箱方式web,excel',
        cartonWebType:
          type: string
          description: web装箱方式
        cartonFile:
          type: string
          description: excel的装箱文件
        cartonFeedStatus:
          type: string
          description: 箱子信息的feed状态
        acceptTransport:
          type: string
          description: 接受运费 0否 1是',
        cartonNum:
          type: string
          description: 箱子数量
        feedMsg:
          type: string
          description: feed错误信息
        shippedTime:
          type: string
          description: '发货时间（在我们系统标记发货时间）   '
        remark:
          type: string
          description: 备注
        remarkColor:
          type: string
          description: 备注颜色
        createId:
          type: string
          description: 创建人ID
        createName:
          type: string
          description: 创建人
        createTime:
          type: string
          description: 创建时间
        updateTime:
          type: string
          description: 更新时间
        mobile:
          type: string
          description: 发件地址电话
        trackNos:
          type: array
          description: 运单号
          items:
            type: string
        shipSnList:
          type: array
          description: 发货单号列表
          items:
            type: string
        weight:
          type: string
          description: 重量 --来源于商品
        volume:
          type: string
          description: 体积 --来源于商品
        isCreated:
          type: string
          description: 是否是在本系统中创建的0:是，1:不是
        trackingNo:
          type: string
          description: 追踪号
        countryCode:
          type: string
          description: countryCode
        referenceId:
          type: string
          description: referenceId
      title: ShipmentOpenVo
      x-apifox-orders:
        - id
        - shopId
        - marketplaceId
        - amazonShipmentId
        - name
        - fromAddress
        - fulfillmentCenterId
        - toAddress
        - labelPrepType
        - labelPrepPreference
        - areCasesRequired
        - skuKinds
        - shipmentStatus
        - transitStatus
        - transitStatusForShipOrder
        - uploadTrack
        - shipmentType
        - isPartnered
        - carrierName
        - markShipped
        - cartonType
        - cartonWebType
        - cartonFile
        - cartonFeedStatus
        - acceptTransport
        - cartonNum
        - feedMsg
        - shippedTime
        - remark
        - remarkColor
        - createId
        - createName
        - createTime
        - updateTime
        - mobile
        - trackNos
        - shipSnList
        - weight
        - volume
        - isCreated
        - trackingNo
        - countryCode
        - referenceId
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    AmznFBAAddressOpenVo:
      type: object
      properties:
        name:
          type: string
          description: 收货人
          examples:
            - Amazon.com Services, Inc.
        addressLine1:
          type: string
          description: 地址1
          examples:
            - 24300 Nandina Ave
        addressLine2:
          type: string
          description: 地址2
        city:
          type: string
          description: 城市
          examples:
            - Moreno Valley
        districtOrCounty:
          type: string
          description: 国家/地区
          examples:
            - 美国(UNITED STATES)
        stateOrProvinceCode:
          type: string
          description: 州/省
          examples:
            - CA
        countryCode:
          type: string
          description: 国家代码
          examples:
            - US
        postalCode:
          type: string
          description: 邮编
          examples:
            - 92551-9534
      title: AmznFBAAddressOpenVo
      x-apifox-orders:
        - name
        - addressLine1
        - addressLine2
        - city
        - districtOrCounty
        - stateOrProvinceCode
        - countryCode
        - postalCode
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
