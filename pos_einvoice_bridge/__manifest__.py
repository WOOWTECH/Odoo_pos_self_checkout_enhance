{
    "name": "POS E-Invoice Bridge (ECPay)",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Integrates ECPay Taiwan e-invoice (電子發票) into POS Self Order Enhancement",
    "description": """
POS E-Invoice Bridge | POS 電子發票橋接模組
=============================================

將綠界電子發票（ecpay_invoice_tw）整合到 POS 自助點餐增強模組中。

此模組為橋接模組，同時依賴 pos_self_order_enhancement 和 ecpay_invoice_tw。
不安裝此模組時，POS 自助點餐模組可獨立運作，不需要電子發票功能。

Features | 功能
---------------
- POS 結帳時自動開立電子發票
- 支援手機條碼、捐贈碼、統一編號三種載具
- 自助點餐頁面的載具輸入介面
- POS 設定頁面的電子發票開關與印表機設定
- 付款完成後自動開立並列印發票
- WebSocket 觸發的發票自動列印
    """,
    "author": "WoowTech",
    "website": "https://aiot.woowtech.io/",
    "license": "LGPL-3",
    "depends": ["pos_self_order_enhancement", "ecpay_invoice_tw"],
    "data": [
        "views/pos_config_einvoice_view.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_einvoice_bridge/static/src/printer/**/*",
            "pos_einvoice_bridge/static/src/pos/**/*",
        ],
        "pos_self_order.assets": [
            "pos_einvoice_bridge/static/src/app/**/*",
        ],
    },
    "installable": True,
    "auto_install": False,
    "application": False,
}
