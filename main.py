import os
import sys
import time
import serial
import serial.tools.list_ports
from fmu_uploader import firmware, uploader
from PyQt5 import QtWidgets, QtGui
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtWidgets import QMessageBox, QFileDialog, QToolTip
from PyQt5.QtCore import QRect, QTimer, pyqtSignal, QThread, QDateTime
from ui import Ui_Form
from sys import platform as _platform


class BackQthread(QThread):
    # 自定义信号为str参数类型
    update_date = pyqtSignal(str)

    def run(self):
        while True:
            # 获得当前系统时间
            data = QDateTime.currentDateTime()
            # 设置时间显示格式
            curTime = data.toString('yyyy-MM-dd hh:mm:ss dddd')
            # 发射信号
            self.update_date.emit(str(curTime))
            # 睡眠一秒
            time.sleep(1)


class Backend_uploadthread(QThread):
    # 自定义信号为str参数类型
    upload_show = pyqtSignal(str)
    upload_progress = pyqtSignal(int)
    upload_exit = pyqtSignal()

    def __init__(self, p_list, port):
        super().__init__()
        print("upload thread init")
        self.p_list = p_list
        self.port = port
        self.target_port = []  # the ports find after push an upload button

    def get_firmware(self, firmware):
        self.bin_file = firmware

    def run(self):
        print("upload thread running")
        try:
            self.fmu_upload()
        finally:
            self.upload_exit.emit()


    # fmu串口自动检测
    def fmu_port_auto_check(self):
        while True:
            try:
                list_tmp = list(serial.tools.list_ports.comports())
                # it seems we just disconnect one port update the port list
                if len(list_tmp) < len(self.p_list):
                    self.p_list = list_tmp
                    time.sleep(0.1)
                    continue

                #
                self.target_port = [val for val in list_tmp if val not in self.p_list]
                if self.target_port:
                    for port in self.target_port:
                        txtCon = "find new port:" + port[0]
                        print(txtCon)
                        self.upload_show.emit(str(txtCon))
                    break
                else:
                    time.sleep(0.05)
                    continue
            except Exception:
                text = "error occur when list serial ports"
                print(text)
                self.upload_show.emit(str(text))

    def fmu_upload(self):
        # if self.firmware_bin is None:
        #     QMessageBox.warning(self, "警告对话框", "请先选择有效的固件！", QMessageBox.Ok)
        #     return

        # warn people about ModemManager which interferes badly with Pixhawk
        if os.path.exists("/usr/sbin/ModemManager"):
            print(
                "==========================================================================================================")
            print(
                "WARNING: You should uninstall ModemManager as it conflicts with any non-modem serial device (like Pixhawk)")
            print(
                "==========================================================================================================")

        # Load the firmware file
        fw = firmware(self.bin_file)
        txtCon = "加载固件到飞控 %d,%x, 大小: %d bytes, 等待飞控 bootloader...\n" % (
            fw.property('board_id'), fw.property('board_revision'), fw.property('image_size'))
        self.upload_show.emit(str(txtCon))
        print(txtCon)
        txtCon = "如果超过3s没有反应,请重新插拔USB接口."
        self.upload_show.emit(str(txtCon))
        print(txtCon)

        # Spin waiting for a device to show up
        try:
            # search a port and open it if it is a fmu-bootloader
            self.fmu_port_auto_check()

            while True:
                for port in self.target_port:

                    print("Trying %s" % port[0])

                    # create an uploader attached to the port
                    try:
                        if "linux" in _platform:
                            # Linux, don't open Mac OS and Win ports
                            if "COM" not in port and "tty.usb" not in port:
                                up = uploader(self.port, port[0], self.upload_show, self.upload_progress, 115200)
                        elif "darwin" in _platform:
                            # OS X, don't open Windows and Linux ports
                            if "COM" not in port and "ACM" not in port:
                                up = uploader(self.port, port[0], self.upload_show, self.upload_progress, 115200)
                        elif "win" in _platform:
                            # Windows, don't open POSIX ports
                            if "/" not in port:
                                up = uploader(self.port, port[0], self.upload_show, self.upload_progress, 115200)
                    except Exception:
                        # open failed, rate-limit our attempts
                        time.sleep(0.05)

                        # and loop to the next port
                        continue

                    found_bootloader = False
                    while (True):
                        up.debug_test()
                        up.open()

                        # port is open, try talking to it
                        try:
                            # identify the bootloader
                            up.identify()
                            found_bootloader = True
                            txtCon = "在串口:%s找到目标板，ID:%d, 版本:%x\nbootloader版本: %x" % (
                                port[0], up.board_type, up.board_rev, up.bl_rev)
                            self.upload_show.emit(str(txtCon))
                            print(txtCon)
                            break

                        except Exception:

                            if not up.send_reboot():
                                break

                            # wait for the reboot, without we might run into Serial I/O Error 5
                            time.sleep(0.5)

                            # always close the port
                            up.close()

                            # wait for the close, without we might run into Serial I/O Error 6
                            time.sleep(0.5)

                    if not found_bootloader:
                        # Go to the next port
                        continue

                    try:
                        # ok, we have a bootloader, try flashing it
                        up.upload(fw, force=False, boot_delay=False)

                    except RuntimeError as ex:
                        # print the error
                        print("\nERROR: %s" % ex.args)

                    except IOError:
                        up.close()
                        continue

                    finally:
                        # always close the port
                        up.close()

                # Delay retries to < 20 Hz to prevent spin-lock from hogging the CPU
                time.sleep(0.05)
                return

        # CTRL+C aborts the upload/spin-lock by interrupt mechanics
        except Exception:
            print("\n Upload aborted by user.")


class Pyqt5_Serial(QtWidgets.QWidget, Ui_Form):

    def __init__(self):
        super(Pyqt5_Serial, self).__init__()
        self.setupUi(self)
        self.ser = serial.Serial(timeout=0.5)

        self.port_list = []  # the ports find on startup
        self.firmware_bin = ""

        # 实例化对象
        self.backend = BackQthread()
        # 信号连接到界面显示槽函数
        self.backend.update_date.connect(self.show_time)
        # 多线程开始
        self.backend.start()

        # 实例化对象
        self.backend_uplaod = Backend_uploadthread(self.port_list, self.ser)
        # 信号连接到界面显示槽函数
        self.backend_uplaod.upload_show.connect(self.show_infoes)
        self.backend_uplaod.upload_exit.connect(self.upload_exit_cb)
        self.backend_uplaod.upload_progress.connect(self.upload_progress_cb)

        self.init()
        self.port_check()
        self.setWindowTitle("SW_Programmer")
        self.setWindowIcon(QIcon('SW_programmer.png'))

        # 接收数据和发送数据数目置零
        self.data_num_received = 0
        self.lineEdit.setText(str(self.data_num_received))
        self.data_num_sended = 0
        self.lineEdit_2.setText(str(self.data_num_sended))

    def init(self):
        # 提示文本字体和大小
        QToolTip.setFont(QFont('SansSerif', 10))

        # 选项卡切换
        self.tabWidget.currentChanged.connect(self.adjust_revarea)

        # 串口检测按钮
        self.s1__box_1.clicked.connect(self.port_check)

        # 串口信息显示
        self.ui_serialchoose.currentTextChanged.connect(self.port_imf)

        # 打开串口按钮
        self.open_button.clicked.connect(self.port_open)

        # 关闭串口按钮
        self.close_button.clicked.connect(self.port_close)

        # 发送数据按钮
        self.s3__send_button.clicked.connect(self.data_send)

        # 定时器接收数据
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.data_receive)

        # 清除发送窗口
        self.s3__clear_button.clicked.connect(self.send_data_clear)

        # 清除接收窗口
        self.s2__clear_button.clicked.connect(self.receive_data_clear)

        # 选择固件
        self.open_file.clicked.connect(self.openFile)

        # 上传固件
        self.upload_button.clicked.connect(self.upload_fw)
        self.upload_button.setToolTip('点击前请先选择固件')

    def show_infoes(self, info):
        print(info)
        if info.startswith('\r'):
            lastLine = self.s2__receive_text.textCursor()
            lastLine.select(QtGui.QTextCursor.LineUnderCursor)
            lastLine.removeSelectedText()
            self.s2__receive_text.moveCursor(QtGui.QTextCursor.StartOfLine, QtGui.QTextCursor.MoveAnchor)
            infoTmp = info.strip("\r")
            self.s2__receive_text.insertPlainText(infoTmp)
        elif "" == info:
            self.s2__receive_text.append(info)
            self.s2__receive_text.repaint()
        else:
            self.s2__receive_text.append(info + "\n")
            self.s2__receive_text.repaint()

    def show_time(self, str_time):
        self.label_time.setText(str_time)

    def adjust_revarea(self):
        if self.tabWidget.tabText(self.tabWidget.currentIndex()) == "串口助手":
            self.s2__receive_text.setGeometry(QRect(197, 50, 391, 282))
        else:
            self.s2__receive_text.setGeometry(QRect(27, 113, 561, 219))

    def upload_exit_cb(self):
        self.upload_button.setEnabled(True)
        # enable tab "串口助手" for exit from firmware upload backend
        self.tabWidget.setTabEnabled(1, True)

    def upload_progress_cb(self, pct):
        self.progressBar_upload.setValue(pct)
    # 串口检测
    def port_check(self):
        # 检测所有存在的串口，将信息存储在字典中
        self.Com_Dict = {}
        self.port_list = list(serial.tools.list_ports.comports())

        self.ui_serialchoose.clear()
        for port in self.port_list:
            self.Com_Dict["%s" % port[0]] = "%s" % port[1]
            self.ui_serialchoose.addItem(port[0])

        print(self.Com_Dict)
        if len(self.Com_Dict) == 0:
            self.ui_serialdisp.setText(" 无串口")

    # 打开串口
    def fmu_port_open(self):
        self.ser.port = self.ui_serialchoose.currentText()
        self.ser.baudrate = 115200
        try:
            self.ser.open()
        except:
            QMessageBox.critical(self, "Port Error", "此串口不能被打开！")
            return None

        # 打开串口接收定时器，周期为2ms
        self.timer.start(2)

        if self.ser.isOpen():
            self.open_button.setEnabled(False)
            self.close_button.setEnabled(True)
            self.formGroupBox1.setTitle("串口状态（已开启）")

    # 串口信息
    def port_imf(self):
        # 显示选定的串口的详细信息
        imf_s = self.ui_serialchoose.currentText()
        if imf_s != "":
            self.ui_serialdisp.setText(self.Com_Dict[self.ui_serialchoose.currentText()])

    # 打开串口
    def port_open(self):
        self.ser.port = self.ui_serialchoose.currentText()
        self.ser.baudrate = int(self.s1__box_3.currentText())
        try:
            self.ser.open()
        except:
            QMessageBox.critical(self, "Port Error", "此串口不能被打开！")
            return None

        # 打开串口接收定时器，周期为2ms
        self.timer.start(2)

        if self.ser.isOpen():
            self.open_button.setEnabled(False)
            self.close_button.setEnabled(True)
            self.formGroupBox1.setTitle("串口状态（已开启）")

    # 关闭串口
    def port_close(self):
        self.timer.stop()
        try:
            self.ser.close()
        except:
            pass
        self.open_button.setEnabled(True)
        self.close_button.setEnabled(False)
        # 接收数据和发送数据数目置零
        self.data_num_received = 0
        self.lineEdit.setText(str(self.data_num_received))
        self.data_num_sended = 0
        self.lineEdit_2.setText(str(self.data_num_sended))
        self.formGroupBox1.setTitle("串口状态（已关闭）")

    # 发送数据
    def data_send(self):
        if self.ser.isOpen():
            input_s = self.s3__send_text.toPlainText()
            if input_s != "":
                # 非空字符串
                if self.hex_send.isChecked():
                    # hex发送
                    input_s = input_s.strip()
                    send_list = []
                    while input_s != '':
                        try:
                            num = int(input_s[0:2], 16)
                        except ValueError:
                            QMessageBox.critical(self, 'wrong data', '请输入十六进制数据，以空格分开!')
                            return None
                        input_s = input_s[2:].strip()
                        send_list.append(num)
                    input_s = bytes(send_list)
                else:
                    # ascii发送
                    input_s = (input_s + '\r\n').encode('utf-8')

                num = self.ser.write(input_s)
                self.data_num_sended += num
                self.lineEdit_2.setText(str(self.data_num_sended))
        else:
            pass

    # 接收数据
    def data_receive(self):
        try:
            num = self.ser.inWaiting()
        except:
            self.port_close()
            return None
        if num > 0:
            data = self.ser.read(num)
            num = len(data)
            # hex显示
            if self.hex_receive.checkState():
                out_s = ''
                for i in range(0, len(data)):
                    out_s = out_s + '{:02X}'.format(data[i]) + ' '
                self.s2__receive_text.insertPlainText(out_s)
            else:
                # 串口接收到的字符串为b'123',要转化成unicode字符串才能输出到窗口中去
                self.s2__receive_text.insertPlainText(data.decode('utf-8'))

            # 统计接收字符的数量
            self.data_num_received += num
            self.lineEdit.setText(str(self.data_num_received))

            # 获取到text光标
            textCursor = self.s2__receive_text.textCursor()
            # 滚动到底部
            textCursor.movePosition(textCursor.End)
            # 设置光标到text中去
            self.s2__receive_text.setTextCursor(textCursor)
        else:
            pass

    # 清除显示
    def send_data_clear(self):
        self.s3__send_text.setText("")

    def receive_data_clear(self):
        self.s2__receive_text.setText("")

    def openFile(self):
        sys.stdout.write("stdout: open file")
        dialog = QFileDialog(self)
        fname = dialog.getOpenFileName(self, "打开文件", '', '*.apj')  # 虽然是静态函数，但先创建实例可以记住上次打开的路径

        if fname[0]:
            with open(fname[0], 'rb') as f:
                print(fname[0])
                txtCon = "".join(fname[0])
                self.s3__send_text_2.setText(txtCon)
                self.firmware_bin = txtCon

    def upload_fw(self):
        #
        self.backend_uplaod.get_firmware(self.firmware_bin)
        # 多线程开始
        self.backend_uplaod.start()
        #
        self.upload_button.setEnabled(False)
        # disable change tab to "串口助手"
        self.tabWidget.setTabEnabled(1, False)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    myshow = Pyqt5_Serial()
    myshow.show()
    sys.exit(app.exec_())
