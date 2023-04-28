# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main_window.ui'
##
## Created by: Qt User Interface Compiler version 5.15.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtWidgets import *


class Ui_main_window(object):
    def setupUi(self, main_window):
        if not main_window.objectName():
            main_window.setObjectName(u"main_window")
        main_window.resize(1156, 750)
        self.quit_action = QAction(main_window)
        self.quit_action.setObjectName(u"quit_action")
        self.etf_dynamic_depth_action = QAction(main_window)
        self.etf_dynamic_depth_action.setObjectName(u"etf_dynamic_depth_action")
        self.future_dynamic_depth_action = QAction(main_window)
        self.future_dynamic_depth_action.setObjectName(u"future_dynamic_depth_action")
        self.team_active_orders_table_action = QAction(main_window)
        self.team_active_orders_table_action.setObjectName(u"team_active_orders_table_action")
        self.action_team_compare = QAction(main_window)
        self.action_team_compare.setObjectName(u"action_team_compare")
        self.actionPrice_Ladder_FUT = QAction(main_window)
        self.actionPrice_Ladder_FUT.setObjectName(u"actionPrice_Ladder_FUT")
        self.profit_loss_chart_action = QAction(main_window)
        self.profit_loss_chart_action.setObjectName(u"profit_loss_chart_action")
        self.action_tile_windows = QAction(main_window)
        self.action_tile_windows.setObjectName(u"action_tile_windows")
        self.midpoint_price_chart_action = QAction(main_window)
        self.midpoint_price_chart_action.setObjectName(u"midpoint_price_chart_action")
        self.team_trade_history_table_action = QAction(main_window)
        self.team_trade_history_table_action.setObjectName(u"team_trade_history_table_action")
        self.all_teams_profit_table_action = QAction(main_window)
        self.all_teams_profit_table_action.setObjectName(u"all_teams_profit_table_action")
        self.tile_subwindows_action = QAction(main_window)
        self.tile_subwindows_action.setObjectName(u"tile_subwindows_action")
        self.central_widget = QWidget(main_window)
        self.central_widget.setObjectName(u"central_widget")
        self.verticalLayout = QVBoxLayout(self.central_widget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.mdi_area = QMdiArea(self.central_widget)
        self.mdi_area.setObjectName(u"mdi_area")
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.mdi_area.sizePolicy().hasHeightForWidth())
        self.mdi_area.setSizePolicy(sizePolicy)

        self.verticalLayout.addWidget(self.mdi_area)

        main_window.setCentralWidget(self.central_widget)
        self.menubar = QMenuBar(main_window)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 1156, 22))
        self.file_menu = QMenu(self.menubar)
        self.file_menu.setObjectName(u"file_menu")
        self.reopen_window_menu = QMenu(self.menubar)
        self.reopen_window_menu.setObjectName(u"reopen_window_menu")
        main_window.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(main_window)
        self.statusbar.setObjectName(u"statusbar")
        main_window.setStatusBar(self.statusbar)

        self.menubar.addAction(self.file_menu.menuAction())
        self.menubar.addAction(self.reopen_window_menu.menuAction())
        self.file_menu.addAction(self.quit_action)
        self.reopen_window_menu.addAction(self.future_dynamic_depth_action)
        self.reopen_window_menu.addAction(self.etf_dynamic_depth_action)
        self.reopen_window_menu.addAction(self.all_teams_profit_table_action)
        self.reopen_window_menu.addAction(self.team_active_orders_table_action)
        self.reopen_window_menu.addAction(self.team_trade_history_table_action)
        self.reopen_window_menu.addAction(self.midpoint_price_chart_action)
        self.reopen_window_menu.addAction(self.profit_loss_chart_action)

        self.retranslateUi(main_window)

        QMetaObject.connectSlotsByName(main_window)
    # setupUi

    def retranslateUi(self, main_window):
        main_window.setWindowTitle(QCoreApplication.translate("main_window", u"Ready Trader Go", None))
        self.quit_action.setText(QCoreApplication.translate("main_window", u"&Quit", None))
        self.etf_dynamic_depth_action.setText(QCoreApplication.translate("main_window", u"&ETF Dynamic Depth", None))
        self.future_dynamic_depth_action.setText(QCoreApplication.translate("main_window", u"&Future Dynamic Depth", None))
        self.team_active_orders_table_action.setText(QCoreApplication.translate("main_window", u"Team Active &Orders Table", None))
        self.action_team_compare.setText(QCoreApplication.translate("main_window", u"Team &Compare", None))
        self.actionPrice_Ladder_FUT.setText(QCoreApplication.translate("main_window", u"Price Ladder : FUT", None))
        self.profit_loss_chart_action.setText(QCoreApplication.translate("main_window", u"&Profit Loss Chart", None))
        self.action_tile_windows.setText(QCoreApplication.translate("main_window", u"Tile &Windows", None))
        self.midpoint_price_chart_action.setText(QCoreApplication.translate("main_window", u"&Midpoint Price Chart", None))
        self.team_trade_history_table_action.setText(QCoreApplication.translate("main_window", u"Team Trade &History Table", None))
        self.all_teams_profit_table_action.setText(QCoreApplication.translate("main_window", u"&All Teams Profit Table", None))
        self.tile_subwindows_action.setText(QCoreApplication.translate("main_window", u"Tile Subwindows", None))
        self.file_menu.setTitle(QCoreApplication.translate("main_window", u"&File", None))
        self.reopen_window_menu.setTitle(QCoreApplication.translate("main_window", u"&Reopen Window", None))
    # retranslateUi

