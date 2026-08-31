# 创建SKU

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/commodity/create.json:
    post:
      summary: 创建SKU
      deprecated: false
      description: ''
      operationId: createUsingPOST
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
              $ref: '#/components/schemas/CommodityCreateOpenVo'
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
      x-order: '6'
      x-apifox-folder: 商品/商品列表
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-51516592-run
components:
  schemas:
    CommodityCreateOpenVo:
      type: object
      required:
        - name
        - sku
        - isGroup
      properties:
        cartonLength:
          type: string
          description: 箱规——长 单位为cm 支持两位小数
        version:
          type: string
          description: API版本, 默认为”1“，带独立装箱规格版本为”2“
        cartonWidth:
          type: string
          description: 箱规——宽 单位为cm 支持两位小数
        name:
          type: string
          description: 商品名称，必填，长度不超过1024
        cartonHeight:
          type: string
          description: 箱规——高 单位为cm 支持两位小数
        sku:
          type: string
          description: SKU，必填，必须为英文或英文符号，长度不超过100
        cartonWeight:
          type: string
          description: 单箱重量  单位为kg 支持两位小数
        isGroup:
          type: string
          description: 商品类型，必传 0表示普通sku,1表示组合sku,2表示加工SKU
        cartonQty:
          type: string
          description: 单箱数量 只能为正整数
        purchaseCost:
          type: string
          description: 采购成本 人民币，支持四位小数
        purchaseCostLock:
          type: integer
          format: int32
          description: 组合、加工商品采购成本锁定 1 - 不锁定，允许自动关联修改；0 - 锁定，只允许手动修改
        wrapCartonLength:
          type: string
          description: 商品包装规格长(cm)
        purchaseDays:
          type: string
          description: 采购时长,仅支持正整数
        wrapCartonWidth:
          type: string
          description: 商品包装规格宽(cm)
        fullCid:
          type: string
          description: 商品分类ID
        wrapCartonHeight:
          type: string
          description: 商品包装规格高(cm)
        remark:
          type: string
          description: 商品备注，长度不超过1024
        wrapCartonWeight:
          type: string
          description: 商品包装重量
        devId:
          type: string
          description: 开发员id，可以从获取子账号接口获取
        wrapCartonWeightUnit:
          type: string
          description: 商品包装重量单位
        needAssembleProcess:
          type: string
          description: 是否需要加工过程，仅加工sku支持，支持true或false
        identificationCode:
          type: string
          description: 识别码 仅支持字母、数字和-_，识别码是自定义码，包括图书印刷行业的ISBN，移动电子通信产品的IME和S/N序列号
        state:
          type: string
          description: 商品状态:0:停售,1:在售,2:开发中,3:待售,4:清仓
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
        autoCalcWeight:
          type: string
          description: 是否自动计算重量, 默认false，（只有组合商品和加工商品生效）
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
        imgUrl:
          type: string
          description: 图片url，必须https或http开头
        declareNameCh:
          type: string
          description: 报关中文名，长度不超过200
        declareNameEn:
          type: string
          description: 报关英文名，长度不超过200，必须为英文
        declareCharge:
          type: string
          description: 报关单价, 单位为USD，支持两位2小数
        declareWeight:
          type: string
          description: 报关重量, 单位为 g，仅支持正整数
        hsCode:
          type: string
          description: 海关编码，长度不超过20位
        declareMaterial:
          type: string
          description: 中文材质
        declareUseTo:
          type: string
          description: 中文用途
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
        purchaserId:
          type: string
          description: 采购员id，可以从获取子账号接口获取
        sourceUrls:
          type: string
          description: 商品来源网址 ，请http或https开头，多个用|隔开，最大长度不超过5000
        processCost:
          type: string
          description: 加工费 RMB支持两位小数
        isNeedQc:
          type: string
          description: 是否开启质检流程，0表示不开启，1开启
        devDate:
          type: string
          description: 开发时间，yyyy-MM-dd
          examples:
            - '2022-01-01'
        childSkus:
          type: array
          description: childSkus,用于组合sku和加工sku对应的子sku
          items:
            $ref: '#/components/schemas/CommodityCreateChildSkuOpenVo'
        supplierCommodityDtoList:
          type: array
          description: 供应商信息
          items:
            $ref: '#/components/schemas/SupplierCommodityOpenDto'
        dangerTransport:
          type: string
          description: 危险运输品，多个值','拼接，1-含电，2-纯电，3-液体，4-粉末，5-膏体，6-带磁
        commoditySizeVOList:
          type: array
          description: 商品箱规信息
          items:
            $ref: '#/components/schemas/CommoditySizeOpenVO'
        logisticsCostList:
          type: array
          description: 头程信息
          items:
            $ref: '#/components/schemas/CommodityLogisticsOpenCost'
        fieldDataList:
          type: array
          description: 自定义字段，需要先去系统维护再拿来用
          items:
            $ref: '#/components/schemas/FieldData'
        auxList:
          type: array
          description: 关联辅料
          items:
            $ref: '#/components/schemas/CommodityAuxDTO'
        tagList:
          type: array
          description: 商品标签
          items:
            $ref: '#/components/schemas/CommodityTagDTO'
        visitorIds:
          type: array
          description: 查看员id，可以从获取子账号接口获取
          items:
            type: integer
            format: int32
        purchaseRemark:
          type: string
          description: 采购备注，最多500字符
        minPurchaseNum:
          type: integer
          format: int32
          description: 最低采购量
        inspectionContent:
          type: string
          description: 质检内容
        inspectionTemplateId:
          type: integer
          format: int64
          description: 质检模板id
      title: CommodityCreateOpenVo
      x-apifox-orders:
        - cartonLength
        - version
        - cartonWidth
        - name
        - cartonHeight
        - sku
        - cartonWeight
        - isGroup
        - cartonQty
        - purchaseCost
        - purchaseCostLock
        - wrapCartonLength
        - purchaseDays
        - wrapCartonWidth
        - fullCid
        - wrapCartonHeight
        - remark
        - wrapCartonWeight
        - devId
        - wrapCartonWeightUnit
        - needAssembleProcess
        - identificationCode
        - state
        - brandId
        - materialQuality
        - unit
        - useTo
        - model
        - autoCalcWeight
        - weight
        - weightUnit
        - length
        - width
        - height
        - imgUrl
        - declareNameCh
        - declareNameEn
        - declareCharge
        - declareWeight
        - hsCode
        - declareMaterial
        - declareUseTo
        - declareModel
        - declareDepartment
        - declareBrandType
        - declareDiscountType
        - declareElements
        - purchaserId
        - sourceUrls
        - processCost
        - isNeedQc
        - devDate
        - childSkus
        - supplierCommodityDtoList
        - dangerTransport
        - commoditySizeVOList
        - logisticsCostList
        - fieldDataList
        - auxList
        - tagList
        - visitorIds
        - purchaseRemark
        - minPurchaseNum
        - inspectionContent
        - inspectionTemplateId
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    CommodityTagDTO:
      type: object
      properties:
        tagId:
          type: integer
          format: int64
          description: tag id
        tagName:
          type: string
          description: tag名字
      title: CommodityTagDTO
      x-apifox-orders:
        - tagId
        - tagName
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    CommodityAuxDTO:
      type: object
      properties:
        auxId:
          type: integer
          format: int64
          description: 辅料id
        auxSku:
          type: string
          description: 辅料sku
        commodityNum:
          type: integer
          format: int32
          description: 商品数
        auxNum:
          type: integer
          format: int32
          description: 辅料数
      title: CommodityAuxDTO
      x-apifox-orders:
        - auxId
        - auxSku
        - commodityNum
        - auxNum
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FieldData:
      type: object
      properties:
        fieldId:
          type: integer
          format: int64
          description: 自定义字段id
        fieldName:
          type: string
          description: 自定义字段id
        values:
          type: array
          description: 自定义字段值
          items:
            type: string
      title: FieldData
      x-apifox-orders:
        - fieldId
        - fieldName
        - values
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    CommodityLogisticsOpenCost:
      type: object
      properties:
        marketplaceId:
          type: string
          description: 站点，为Amazon站点ID，详见开发指南>>站点对应关系
        headTripCost:
          type: number
          description: fba头程费用
        clearanceHsCode:
          type: string
          description: 清关hscode
        clearancePrice:
          type: number
          description: 清关单价
        clearancePriceUnit:
          type: string
          description: 清关单价
        fbaDeclareRate:
          type: number
          description: FBA货件报关税率
        link:
          type: string
          description: 产品链接
        remark:
          type: string
          description: 备注
      title: CommodityLogisticsOpenCost
      x-apifox-orders:
        - marketplaceId
        - headTripCost
        - clearanceHsCode
        - clearancePrice
        - clearancePriceUnit
        - fbaDeclareRate
        - link
        - remark
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    CommoditySizeOpenVO:
      type: object
      properties:
        cartonLength:
          type: string
          description: 箱规——长 单位为cm 支持两位小数
        id:
          type: string
          description: ID
        cartonWidth:
          type: string
          description: 箱规——宽 单位为cm 支持两位小数
        templateName:
          type: string
          description: 箱规名称
        cartonHeight:
          type: string
          description: 箱规——高 单位为cm 支持两位小数
        cartonWeight:
          type: string
          description: 单箱重量  单位为kg 支持两位小数
        cartonQty:
          type: string
          description: 单箱数量 只能为正整数
        wrapCartonLength:
          type: string
          description: 商品包装规格长(cm)
        wrapCartonWidth:
          type: string
          description: 商品包装规格宽(cm)
        wrapCartonHeight:
          type: string
          description: 商品包装规格高(cm)
        wrapCartonWeight:
          type: string
          description: 商品包装重量
        wrapCartonWeightUnit:
          type: string
          description: 商品包装重量单位
      title: CommoditySizeOpenVO
      x-apifox-orders:
        - cartonLength
        - id
        - cartonWidth
        - templateName
        - cartonHeight
        - cartonWeight
        - cartonQty
        - wrapCartonLength
        - wrapCartonWidth
        - wrapCartonHeight
        - wrapCartonWeight
        - wrapCartonWeightUnit
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    SupplierCommodityOpenDto:
      type: object
      properties:
        supplierId:
          type: string
          description: 供应商ID，可从获取供应商接口获取
        sourceUrl:
          type: string
          description: 商品链接(https://或http:开头)
        supplier1688Vo:
          type: array
          description: 1688供应商信息
          items:
            $ref: '#/components/schemas/SupplierCommodity1688OpenVo'
        isMain:
          type: boolean
          description: 是否首选供应商
        purchase:
          type: string
          description: 采购单价
        pairingType:
          type: string
          description: 配对类型：1单个 2多个
        extraInfoModel:
          $ref: '#/components/schemas/CommoditySupplierExtraInfoModel'
      title: SupplierCommodityOpenDto
      x-apifox-orders:
        - supplierId
        - sourceUrl
        - supplier1688Vo
        - isMain
        - purchase
        - pairingType
        - extraInfoModel
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    CommoditySupplierExtraInfoModel:
      type: object
      properties:
        priceRangeList:
          type: array
          description: 采购价区间
          items:
            $ref: '#/components/schemas/SupplierPriceRange'
      title: CommoditySupplierExtraInfoModel
      x-apifox-orders:
        - priceRangeList
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    SupplierPriceRange:
      type: object
      properties:
        minPurchaseQuantity:
          type: integer
          format: int32
          description: 最小采购数量
        purchase:
          type: number
          description: 采购单价
        priceIncludeTax:
          type: number
          description: 含税价
      title: SupplierPriceRange
      x-apifox-orders:
        - minPurchaseQuantity
        - purchase
        - priceIncludeTax
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    SupplierCommodity1688OpenVo:
      type: object
      properties:
        supplier:
          type: string
          description: 1688供应商
        productId:
          type: string
          description: 1688商品id
        title:
          type: string
          description: 1688商品标题
        sourceUrl:
          type: string
          description: 来源url
        skuId:
          type: string
          description: skuId
        specId:
          type: string
          description: specId
        attrs:
          type: array
          description: 变种属性
          items:
            $ref: '#/components/schemas/Attr'
        attrDisplay:
          type: string
          description: 规格，展示用
        imgUrl:
          type: string
          description: 图片
        priceRanges:
          type: array
          description: 区间价格。按数量范围设定的区间价格
          items:
            $ref: '#/components/schemas/PriceRange'
        retailprice:
          type: string
          description: 建议零售价，国际站无需关注
      title: SupplierCommodity1688OpenVo
      x-apifox-orders:
        - supplier
        - productId
        - title
        - sourceUrl
        - skuId
        - specId
        - attrs
        - attrDisplay
        - imgUrl
        - priceRanges
        - retailprice
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    PriceRange:
      type: object
      properties:
        startQuantity:
          type: string
          description: 数量
        price:
          type: string
          description: 价格
      title: PriceRange
      x-apifox-orders:
        - startQuantity
        - price
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    Attr:
      type: object
      properties:
        id:
          type: string
          description: 属性id
        name:
          type: string
          description: 属性名
        valueId:
          type: string
          description: 属性值id
        value:
          type: string
          description: 属性值
      title: Attr
      x-apifox-orders:
        - id
        - name
        - valueId
        - value
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    CommodityCreateChildSkuOpenVo:
      type: object
      properties:
        childId:
          type: string
          description: childId
        sku:
          type: string
          description: sku
        num:
          type: string
          description: 数量
      title: CommodityCreateChildSkuOpenVo
      x-apifox-orders:
        - childId
        - sku
        - num
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
