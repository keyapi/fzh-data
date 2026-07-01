# SP广告活动

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/cpc/manageData/spCampaign.json:
    post:
      summary: SP广告活动
      deprecated: false
      description: ''
      operationId: spCampaignUsingPOST
      tags:
        - 广告/基础数据
        - 广告-基础数据
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
              $ref: '#/components/schemas/ManageDataCampaignReqVo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABManageDataBaseRespVo%C2%ABManageDataSpCampaign%C2%BB%C2%BB
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
      x-order: '2'
      x-apifox-folder: 广告/基础数据
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-367482273-run
components:
  schemas:
    ManageDataCampaignReqVo:
      type: object
      required:
        - shopId
      properties:
        shopId:
          type: string
          description: 店铺id
        state:
          type: string
          description: 运行状态, 开启:enabled, 暂停:paused, 归档:archived, 不传默认查询全部
        pageSize:
          type: string
          description: 每页条数, 不传默认100, 支持100~1000
        portfolioId:
          type: string
          description: 广告组合id
        campaignId:
          type: string
          description: 广告活动id
        nextToken:
          type: string
          description: 分页游标, 为空则查第一页, 使用该值查询下一页的数据(此时其余条件均失效使用第一页时的条件)
      title: ManageDataCampaignReqVo
      x-apifox-orders:
        - shopId
        - state
        - pageSize
        - portfolioId
        - campaignId
        - nextToken
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«ManageDataBaseRespVo«ManageDataSpCampaign»»:
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
          $ref: >-
            #/components/schemas/ManageDataBaseRespVo%C2%ABManageDataSpCampaign%C2%BB
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«ManageDataBaseRespVo«ManageDataSpCampaign»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ManageDataBaseRespVo«ManageDataSpCampaign»:
      type: object
      properties:
        nextToken:
          type: string
          description: 分页游标, 有值则说明有下一页, 使用该值查询下一页的数据(此时其余条件均失效使用第一页时的条件, 超时时间1分钟)
        itemList:
          type: array
          description: 数据集
          items:
            $ref: '#/components/schemas/ManageDataSpCampaign'
      title: ManageDataBaseRespVo«ManageDataSpCampaign»
      x-apifox-orders:
        - nextToken
        - itemList
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ManageDataSpCampaign:
      type: object
      properties:
        shopId:
          type: string
          description: 店铺id
        state:
          type: string
          description: 运行状态
        portfolioId:
          type: string
          description: 广告组合id
        campaignId:
          type: string
          description: 广告活动id
        name:
          type: string
          description: 活动名称
        targetingType:
          type: string
          description: 投放类型(manual手动，auto自动)
        budget:
          type: string
          description: 每日预算
        servingStatus:
          type: string
          description: 服务状态
        offAmazonBudgetControlStrategy:
          type: string
          description: 亚马逊站外预算控制策略(MAXIMIZE_REACH扩大受众触达，MINIMIZE_SPEND限制在亚马逊站外的花费，空表示没有)
        campaignSite:
          type: string
          description: 站点限制(AMAZON_BUSINESS企业购，AMAZON_HAUL亚马逊HAUL，空表示没有)
        strategy:
          type: string
          description: 竞价策略(legacyForSales仅降低，autoForSales提高和降低，manual固定竞价)
        adjustments:
          type: string
          description: 根据广告位调整竞价
        startDate:
          type: string
          description: 活动开始时间
        endDate:
          type: string
          description: 活动结束时间
        creationDate:
          type: string
          description: 创建时间(yyyy-MM-dd HH:mm:ss)
        lastUpdatedDate:
          type: string
          description: 更新时间(yyyy-MM-dd HH:mm:ss)
      title: ManageDataSpCampaign
      x-apifox-orders:
        - shopId
        - state
        - portfolioId
        - campaignId
        - name
        - targetingType
        - budget
        - servingStatus
        - offAmazonBudgetControlStrategy
        - campaignSite
        - strategy
        - adjustments
        - startDate
        - endDate
        - creationDate
        - lastUpdatedDate
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
