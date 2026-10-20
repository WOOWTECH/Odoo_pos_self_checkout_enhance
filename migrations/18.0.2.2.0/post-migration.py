# -*- coding: utf-8 -*-
"""Post-migration 18.0.2.2.0：既有安裝維持原本外觀。

18.0.2.2.0 把兩個原本寫死的客製改成開關，預設關：
- ``pos.config.self_ordering_black_theme``：自助點餐前端黑色按鈕主題
- ``pos.printer.escpos_square_ticket``：伺服器端廚房單正方形下限

目前實際裝著這顆的 DB 跑的是平台映像那份 18.0.2.0.0，它寫死了黑色按鈕與
正方形廚房單。為了升級後外觀不變，從 18.0.2.2.0 以前的任何版本升級上來
（18.0.2.0.0、18.0.2.1.0 都會跑這支）一律把既有紀錄打開；不要的店家升級後
自己在設定關掉。乾淨安裝不會跑 migration，維持預設關（Odoo 原色、一般長度
廚房單）。
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("UPDATE pos_config SET self_ordering_black_theme = TRUE")
    _logger.info(
        "post-migration 18.0.2.2.0: self_ordering_black_theme on for %s pos.config",
        cr.rowcount,
    )
    cr.execute("UPDATE pos_printer SET escpos_square_ticket = TRUE")
    _logger.info(
        "post-migration 18.0.2.2.0: escpos_square_ticket on for %s pos.printer",
        cr.rowcount,
    )
