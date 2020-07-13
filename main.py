import os
import sys
import time
import threading
import serial
import serial.tools.list_ports
from fmu_uploader import firmware, uploader, debug_test
from PyQt5 import QtWidgets, QtGui
from PyQt5.QtWidgets import QMessageBox, QFileDialog
from PyQt5.QtCore import QTimer, pyqtSignal
from ui import Ui_Form
from sys import platform as _platform

class Pyqt5_Serial(QtWidgets.QWidget, Ui_Form):
    show_infoes_signal = pyqtSignal(str)

    def __init__(self):
        super(Pyqt5_Serial, self).__init__()
        self.setupUi(self)

        self.init()
        self.setWindowTitle("SW_Programer")
        self.ser = serial.Serial(timeout=0.5)
        self.port_list = []                     #the ports find on startup
        self.target_port = []                   #the ports find after push an upload button
        self.port_check()
        self.firmware_bin = "E:\Python\src\SerialProgrammer\arducopter_st3.apj"

        # 接收数据和发送数据数目置零
        self.data_num_received = 0
        self.lineEdit.setText(str(self.data_num_received))
        self.data_num_sended = 0
        self.lineEdit_2.setText(str(self.data_num_sended))

    def init(self):
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

        #选择固件
        self.open_file.clicked.connect(self.openFile)

        #上传固件
        self.upload_button.clicked.connect(self.fmu_upload)

        self.show_infoes_signal.connect(self.show_infoes)

    def show_infoes(self, info):
        print(info)
        self.s2__receive_text.append(info + "\n")
        self.s2__receive_text.repaint()

    # 串口检测
    def port_check(self):
        # 检测所有存在的串口，将信息存储在字典中
        self.Com_Dict = {}
        self.port_list = list(serial.tools.list_ports.comports())

        self.ui_serialchoose.clear()
        for port in self.port_list:

            self.Com_Dict["%s" % port[0]] = "%s" % port[1]
            self.ui_serialchoose.addItem(port[0])
            print(self.ui_serialchoose.currentText())
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
        fname = QFileDialog.getOpenFileName(
            #self, "打开文件", '','*.txt',None,QFileDialog.DontUseNativeDialog)   记住上次打开的路径，被实现
            self, "打开文件", './', '*.apj')
        if fname[0]:
            with open(fname[0],'rb') as f:
                print(fname[0])
                txtCon = "".join(fname[0])
                self.s3__send_text_2.setText(txtCon)
                self.firmware_bin = txtCon


    # fmu串口自动检测
    def fmu_port_auto_check(self):
        while(True):
            try:
                list_tmp = list(serial.tools.list_ports.comports())
                #it seems we just disconnect one port update the port list
                if len(list_tmp) < len(self.port_list):
                    self.port_list = list_tmp
                    time.sleep(0.1)
                    continue

                #
                self.target_port = [val for val in list_tmp if val not in self.port_list]
                if self.target_port:
                    for port in self.target_port:
                        print("find new port:", port[0])
                    break
                else:
                    time.sleep(0.05)
                    continue
            except Exception:
                print("error occur when list serial ports")


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
        fw = firmware(self.firmware_bin)
        txtCon = "加载固件到飞控 %d,%x, 大小: %d bytes, 等待飞控 bootloader...\n" % (fw.property('board_id'), fw.property('board_revision'), fw.property('image_size'))
        self.s2__receive_text.append(txtCon)
        # self.s2__receive_text.repaint()
        print(txtCon)
        txtCon = "如果超过3s没有反应,请重新插拔USB接口."
        self.s2__receive_text.append(txtCon)
        self.s2__receive_text.repaint()
        print(txtCon)

        try:
            debug_test()
            return
        except Exception:
            return

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
                                up = uploader(self.ser, port[0], self.show_infoes_signal, 115200)
                        elif "darwin" in _platform:
                            # OS X, don't open Windows and Linux ports
                            if "COM" not in port and "ACM" not in port:
                                up = uploader(self.ser, port[0], self.show_infoes_signal, 115200)
                        elif "win" in _platform:
                            # Windows, don't open POSIX ports
                            if "/" not in port:
                                up = uploader(self.ser, port[0], self.show_infoes_signal, 115200)
                    except Exception:
                        # open failed, rate-limit our attempts
                        time.sleep(0.05)

                        # and loop to the next port
                        continue

                    found_bootloader = False
                    while (True):
                        up.open()

                        # port is open, try talking to it
                        try:
                            # identify the bootloader
                            up.identify()
                            found_bootloader = True
                            txtCon = "在串口:%s找到目标板，ID:%d, 版本:%x\nbootloader版本: %x"% (
                            port[0], up.board_type, up.board_rev, up.bl_rev)
                            self.show_infoes_signal.emit(txtCon)
                            #self.s2__receive_text.append(txtCon)
                            # self.s2__receive_text.repaint()
                            print(txtCon)
                            break

                        except Exception:

                            if not up.send_reboot():
                                break

                            # wait for the reboot, without we might run into Serial I/O Error 5
                            time.sleep(0.25)

                            # always close the port
                            up.close()

                            # wait for the close, without we might run into Serial I/O Error 6
                            time.sleep(0.3)

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


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    myshow = Pyqt5_Serial()
    myshow.show()
    sys.exit(app.exec_())