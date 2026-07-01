# 创建SPU

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/commodity/insertMultiattributeCommodityV2.json:
    post:
      summary: 创建SPU
      deprecated: false
      description: ''
      operationId: insertMultiattributeCommodityV2UsingPOST
      tags:
        - 商品/商品列表
        - 商品列表
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
              $ref: '#/components/schemas/CommoditySpuCreateOpenVo'
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
      x-apifox-folder: 商品/商品列表
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-51516599-run
components:
  schemas:
    CommoditySpuCreateOpenVo:
      type: object
      required:
        - spu
        - spuName
      properties:
        commodityList:
          type: array
          items:
            $ref: '#/components/schemas/CommodityOpenVo2'
        spu:
          type: string
          description: spu
        spuName:
          type: string
          description: spuName
        spuImgUrl:
          type: string
          description: spu图片地址
        spuDevId:
          type: string
          description: spu 开发员ID
      title: CommoditySpuCreateOpenVo
      x-apifox-orders:
        - commodityList
        - spu
        - spuName
        - spuImgUrl
        - spuDevId
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    CommodityOpenVo2:
      type: object
      required:
        - sku
        - name
        - attributeValueVoList
      properties:
        attributes:
          type: string
        sku:
          type: string
          description: SKU，必填，必须为英文或英文符号，长度不超过100
        name:
          type: string
          description: 商品名称，必填，长度不超过1024
        brandId:
          type: string
          description: 品牌Id
        materialQuality:
          type: string
          description: 材质
        unit:
          type: string
          description: 单位
        useTo:
          type: string
          description: 用途
        model:
          type: string
          description: 型号
        imgUrl:
          type: string
          description: 图片url，必须https或http开头
        purchaseCost:
          type: string
          description: 采购成本 人民币，支持四位小数
        sourceUrls:
          type: string
          description: 商品来源网址 ，请http或https开头，多个用|隔开，最大长度不超过5000
        weight:
          type: string
          description: 重量，默认g
        weightUnit:
          type: string
          description: '重量单位: 可选 克(g)、千克(kg)、磅(lb)、盎司(oz), 不传默认克'
        length:
          type: string
          description: 商品长，单位为cm，支持两位小数
        width:
          type: string
          description: 商品宽，单位为cm，支持两位小数
        height:
          type: string
          description: 商品高，单位为cm，支持两位小数
        cartonLength:
          type: string
          description: 箱规——长 单位为cm 支持两位小数
        cartonWidth:
          type: string
          description: 箱规——宽 单位为cm 支持两位小数
        cartonHeight:
          type: string
          description: 箱规——高 单位为cm 支持两位小数
        cartonWeight:
          type: string
          description: 单箱重量  单位为kg 支持两位小数
        cartonQty:
          type: string
          description: 单箱数量 只能为正整数
        declareNameCh:
          type: string
          description: 报关中文名，长度不超过200
        declareNameEn:
          type: string
          description: 报关英文名，长度不超过200，必须为英文
        declareCharge:
          type: string
          description: 报关单价, 单位为USD，支持两位2小数
        hsCode:
          type: string
          description: 海关编码 长度不超过20位
        declareMaterial:
          type: string
          description: 中文材质
        declareUseTo:
          type: string
          description: 中文用途
        declareMaterialEn:
          type: string
          description: 英文材质
        declareUseToEn:
          type: string
          description: 英文用途
        declareModel:
          type: string
          description: 报关型号
        declareDepartment:
          type: string
          description: 报关单位
        declareBrandType:
          type: string
          description: >-
            报关品牌类型: 0:未选择,1:无品牌,2:境内自主品牌3:境内收购品牌,4:境外品牌(贴牌生产)5:境外品牌(其他)*  具体值见
            CommodityDeclareBrandTypeEnum
        declareDiscountType:
          type: string
          description: 报关出口享惠情况 0:未选择 1:享惠;2:不享惠;3:不确定享受情况
        declareElements:
          type: string
          description: 申报要素
        remark:
          type: string
          description: 备注
        devId:
          type: string
          description: 开发员id，可以从获取子账号接口获取
        fullCid:
          type: string
          description: 商品分类ID
        attributeValueVoList:
          type: array
          description: 商品属性信息
          items:
            $ref: '#/components/schemas/CommodityAttributeValueOpenVo'
        state:
          type: string
          description: 商品状态(1在售，0停售)，默认为1
      title: CommodityOpenVo2
      x-apifox-orders:
        - attributes
        - sku
        - name
        - brandId
        - materialQuality
        - unit
        - useTo
        - model
        - imgUrl
        - purchaseCost
        - sourceUrls
        - weight
        - weightUnit
        - length
        - width
        - height
        - cartonLength
        - cartonWidth
        - cartonHeight
        - cartonWeight
        - cartonQty
        - declareNameCh
        - declareNameEn
        - declareCharge
        - hsCode
        - declareMaterial
        - declareUseTo
        - declareMaterialEn
        - declareUseToEn
        - declareModel
        - declareDepartment
        - declareBrandType
        - declareDiscountType
        - declareElements
        - remark
        - devId
        - fullCid
        - attributeValueVoList
        - state
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    CommodityAttributeValueOpenVo:
      type: object
      required:
        - attributeValueId
      properties:
        attributeValueId:
          type: integer
          format: int64
          description: 属性值Id
      title: CommodityAttributeValueOpenVo
      x-apifox-orders:
        - attributeValueId
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
