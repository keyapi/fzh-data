# Walmart-获取WFS库存列表

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /openapi/psi/walmart/wfsStock/pageList.json:
    post:
      summary: Walmart-获取WFS库存列表
      deprecated: false
      description: ''
      operationId: stockPageListUsingPOST
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
              $ref: '#/components/schemas/WfsStockPageOpenQO'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABWfsStockOpenVO%C2%BB%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-510029215-run
components:
  schemas:
    WfsStockPageOpenQO:
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
      title: WfsStockPageOpenQO
      x-apifox-orders:
        - shopId
        - pageNo
        - pageSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«Page«WfsStockOpenVO»»:
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
          $ref: '#/components/schemas/Page%C2%ABWfsStockOpenVO%C2%BB'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«WfsStockOpenVO»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    Page«WfsStockOpenVO»:
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
            $ref: '#/components/schemas/WfsStockOpenVO'
      title: Page«WfsStockOpenVO»
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    WfsStockOpenVO:
      type: object
      properties:
        id:
          type: integer
          format: int64
          description: 主键ID
        itemId:
          type: integer
          format: int64
          description: WFS平台产品ID
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
        devId:
          type: integer
          format: int64
          description: 开发员ID
        devName:
          type: string
          description: 开发员名称
        gtin:
          type: string
          description: GTIN
        productStatus:
          type: string
          description: 产品状态码
        productStatusName:
          type: string
          description: 产品状态名称
        imgUrl:
          type: string
          description: 图片URL
        purchaseCost:
          type: number
          description: 采购单价
        totalQty:
          type: integer
          format: int32
          description: 总库存
        totalQtyCost:
          type: number
          description: 总库存成本
        availableQty:
          type: integer
          format: int32
          description: 可用库存
        availableQtyCost:
          type: number
          description: 可用库存成本
        onPassageQty:
          type: integer
          format: int32
          description: 在途库存
        onPassageQtyCost:
          type: number
          description: 在途库存成本
        notAvailableQty:
          type: integer
          format: int32
          description: 不可用库存
        notAvailableQtyCost:
          type: number
          description: 不可用库存成本
        suggestReplenishQty:
          type: integer
          format: int32
          description: 建议补货数
        suggestReplenishQtyCost:
          type: number
          description: 建议补货成本
        inv0To90Qty:
          type: integer
          format: int32
          description: 库龄0-90天库存
        inv0To90QtyCost:
          type: number
          description: 库龄0-90天库存成本
        inv91To180Qty:
          type: integer
          format: int32
          description: 库龄91-180天库存
        inv91To180QtyCost:
          type: number
          description: 库龄91-180天库存成本
        inv181To270Qty:
          type: integer
          format: int32
          description: 库龄181-270天库存
        inv181To270QtyCost:
          type: number
          description: 库龄181-270天库存成本
        inv271To365Qty:
          type: integer
          format: int32
          description: 库龄271-365天库存
        inv271To365QtyCost:
          type: number
          description: 库龄271-365天库存成本
        inv365PlusQty:
          type: integer
          format: int32
          description: 库龄365天以上库存
        inv365PlusQtyCost:
          type: number
          description: 库龄365天以上库存成本
        lastThirtyInstockQty:
          type: integer
          format: int32
          description: 近30天入库
        lastThirtyInstockQtyCost:
          type: number
          description: 近30天入库成本
        lastThirtyPlanInstockQty:
          type: integer
          format: int32
          description: 近30天计划入库
        lastThirtyPlanInstockQtyCost:
          type: number
          description: 近30天计划入库成本
        createId:
          type: integer
          format: int64
          description: 创建人ID
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
      title: WfsStockOpenVO
      x-apifox-orders:
        - id
        - itemId
        - wfsProductId
        - shopAuthId
        - shopAuthName
        - sellerSku
        - commodityName
        - commodityId
        - commoditySku
        - commodityType
        - devId
        - devName
        - gtin
        - productStatus
        - productStatusName
        - imgUrl
        - purchaseCost
        - totalQty
        - totalQtyCost
        - availableQty
        - availableQtyCost
        - onPassageQty
        - onPassageQtyCost
        - notAvailableQty
        - notAvailableQtyCost
        - suggestReplenishQty
        - suggestReplenishQtyCost
        - inv0To90Qty
        - inv0To90QtyCost
        - inv91To180Qty
        - inv91To180QtyCost
        - inv181To270Qty
        - inv181To270QtyCost
        - inv271To365Qty
        - inv271To365QtyCost
        - inv365PlusQty
        - inv365PlusQtyCost
        - lastThirtyInstockQty
        - lastThirtyInstockQtyCost
        - lastThirtyPlanInstockQty
        - lastThirtyPlanInstockQtyCost
        - createId
        - createTime
        - updateId
        - updateTime
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
