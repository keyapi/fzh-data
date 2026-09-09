# Mercado-Full库存列表

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /openapi/psi/mercado/fullInventory/pageList.json:
    post:
      summary: Mercado-Full库存列表
      deprecated: false
      description: ''
      operationId: pageListUsingPOST_11
      tags:
        - 多平台/平台仓
        - Mercado-Full库存
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
              $ref: '#/components/schemas/MercadoFullInventoryPageOpenQO'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABMercadoFullInventoryOpenVO%C2%BB%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-510029210-run
components:
  schemas:
    MercadoFullInventoryPageOpenQO:
      type: object
      required:
        - pageNo
        - pageSize
      properties:
        shopId:
          type: string
          description: 店铺ID
        pageNo:
          type: string
          description: 第几页
        pageSize:
          type: string
          description: 每页大小
      title: MercadoFullInventoryPageOpenQO
      x-apifox-orders:
        - shopId
        - pageNo
        - pageSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«Page«MercadoFullInventoryOpenVO»»:
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
          $ref: '#/components/schemas/Page%C2%ABMercadoFullInventoryOpenVO%C2%BB'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«MercadoFullInventoryOpenVO»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    Page«MercadoFullInventoryOpenVO»:
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
            $ref: '#/components/schemas/MercadoFullInventoryOpenVO'
      title: Page«MercadoFullInventoryOpenVO»
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    MercadoFullInventoryOpenVO:
      type: object
      properties:
        itemId:
          type: string
          description: 产品ID
        msku:
          type: string
          description: MSKU
        inventoryId:
          type: string
          description: ML Code
        variationId:
          type: string
          description: 变体id
        pid:
          type: string
          description: 平台产品id
        skuId:
          type: string
          description: 平台商品skuId
        commodityId:
          type: integer
          format: int64
          description: 商品Id
        commodityType:
          type: integer
          format: int32
          description: 商品类型
        commodityImgUrl:
          type: string
          description: 商品图片
        shopType:
          type: string
          description: 店铺类型
        marketPlaceName:
          type: string
          description: 站点名
        shopMarketPlace:
          type: string
          description: 店铺站点
        totalCost:
          type: number
          description: 在库总库存成本
        availableCost:
          type: number
          description: 可售库存成本
        notAvailableCost:
          type: number
          description: 不可售库存成本
        damaged:
          type: integer
          format: int32
          description: 损坏
        notSupported:
          type: integer
          format: int32
          description: 不支持
        commoditySku:
          type: string
          description: 商品SKU
        commodityName:
          type: string
          description: 商品名称
        image:
          type: string
          description: 产品图片URL
        shopId:
          type: integer
          format: int64
          description: 店铺ID
        shopName:
          type: string
          description: 店铺名称
        marketPlaceCode:
          type: string
          description: 站点
        total:
          type: integer
          format: int32
          description: 总库存
        availableQuantity:
          type: integer
          format: int32
          description: 可售库存
        notAvailableQuantity:
          type: integer
          format: int32
          description: 不可售库存
        arrivedDamaged:
          type: integer
          format: int32
          description: 损坏-卖家发货时已损坏
        damagedInFull:
          type: integer
          format: int32
          description: 损坏-在Full仓库内损坏
        dimensionsExceeds:
          type: integer
          format: int32
          description: 不支持-尺寸超限
        expirationProblem:
          type: integer
          format: int32
          description: 不支持-过期问题
        packageProblem:
          type: integer
          format: int32
          description: 不支持-包装问题
        flammable:
          type: integer
          format: int32
          description: 不支持-易燃易爆
        regulationProblem:
          type: integer
          format: int32
          description: 不支持-合规问题
        other:
          type: integer
          format: int32
          description: 不支持-其他
        multipleIdentifier:
          type: integer
          format: int32
          description: 不支持-重复产品ID
        emptyIdentifier:
          type: integer
          format: int32
          description: 不支持-无产品ID
        multipleSku:
          type: integer
          format: int32
          description: 不支持-重复SKU
        invalidIdentifier:
          type: integer
          format: int32
          description: 不支持-无效产品ID
        returnProblem:
          type: integer
          format: int32
          description: 不支持-退货问题
        lost:
          type: integer
          format: int32
          description: 丢失
        withdrawal:
          type: integer
          format: int32
          description: 预留待移除
        noFiscalCoverage:
          type: integer
          format: int32
          description: 未提供税号
        internalProcess:
          type: integer
          format: int32
          description: 内部处理
        transfer:
          type: integer
          format: int32
          description: 转移
        purchaseCost:
          type: number
          description: 采购单价
      title: MercadoFullInventoryOpenVO
      x-apifox-orders:
        - itemId
        - msku
        - inventoryId
        - variationId
        - pid
        - skuId
        - commodityId
        - commodityType
        - commodityImgUrl
        - shopType
        - marketPlaceName
        - shopMarketPlace
        - totalCost
        - availableCost
        - notAvailableCost
        - damaged
        - notSupported
        - commoditySku
        - commodityName
        - image
        - shopId
        - shopName
        - marketPlaceCode
        - total
        - availableQuantity
        - notAvailableQuantity
        - arrivedDamaged
        - damagedInFull
        - dimensionsExceeds
        - expirationProblem
        - packageProblem
        - flammable
        - regulationProblem
        - other
        - multipleIdentifier
        - emptyIdentifier
        - multipleSku
        - invalidIdentifier
        - returnProblem
        - lost
        - withdrawal
        - noFiscalCoverage
        - internalProcess
        - transfer
        - purchaseCost
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
