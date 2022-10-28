#!/usr/bin/env python
# coding=utf-8

import os
import subprocess
import datetime

def exec_command(command):
    cmd = command.encode('utf8', 'ignore')
    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            close_fds=True, shell=True, preexec_fn=os.setsid)
        stdout, stderr = process.communicate()
    except OSError, exp:
        stderr = exp.__str__()
        stdout = stdin = ''
    return '',stdout.splitlines(),stderr.splitlines()

def get_pidmax():
    raw = r""" cat /proc/sys/kernel/pid_max  """
    stdin, stdout, stderr = exec_command(raw)
    pid_max = int(stdout[0])
    raw = r""" ps -efL|wc -l  """
    stdin, stdout, stderr = exec_command(raw)
    pid_real = int(stdout[0])
    if 100*float(pid_real/pid_max) > 0.5 or pid_max < 32768 :
        return True, u"pid_max参数太小(%s)或ps -efL|wc -l(%s)已接近pid_max，需调增优化" % (pid_max,pid_real)
    else :
        return False, []

def get_user_pid_used():
    #pids.current/pids.max 大于50%的输出告警，格式如下
    #/sys/fs/cgroup/pids/user.slice/user-6351.slice max=12288 cur=1102 used%=8.9681
    
    raw = r""" find  /sys/fs/cgroup/pids/user.slice  -maxdepth 1  -type d  -name "user-*"   -exec awk 'BEGIN{ max=0;cur=0 }{if (NR == 1){ max=$1} else if (NR == 2){cur =$1}  }END{ if(cur/ma
x >0.5) {print "{}","max="max,"cur="cur,"used%="cur/max*100} }' {}/pids.max {}/pids.current \; """
    stdin, stdout, stderr = exec_command(raw)
    if stdout :
        return True, u"进程/线程数过多，存在运行风险！%s" % "\n".join(stdout)
    else :
        return False, []

def get_ntp_status():
    stdin, stdout, stderr = exec_command('ps -ef|grep ntp|grep -v grep| wc -l')
    ntp_count =  int(stdout[0])
    stdin, stdout, stderr = exec_command('ps -ef|grep chronyd|grep -v grep| wc -l')
    chronyd_count =  int(stdout[0])
    if ntp_count+chronyd_count == 0 :
       return True, u"主机NTP(chronyd)时钟同步进程数量为0" 
    else:
       return False, []

def get_message_status():
    stdin, stdout, stderr = exec_command('grep "The maximum number of pending replies per connection has been reached" messages |grep -v grep| wc -l')
    count1 =  int(stdout[0])
    if count1 > 0 :
       return True, u"messages日志中存在%s条【The maximum number of pending replies per connection has been reached】报错！" % count1
    else:
       return False, []

def get_load():
    # We are looking for a line like
    #0.19 0.17 0.15 1/616 3634 4
    # l1  l5   l15  _     _    nb_cpus
    raw = r"""echo "$(cat /proc/loadavg) $(grep -E '^CPU|^processor' < /proc/cpuinfo | wc -l)" """
    stdin, stdout, stderr = exec_command(raw)
    line = [l for l in stdout][0].strip()

    load1, load5, load15, _, _, nb_cpus = (line.split(' '))
    load1 = float(load1)
    load5 = float(load5)
    load15 = float(load15)
    nb_cpus = int(nb_cpus)

    w1, w5, w15 = (1,1,1)
    c1, c5, c15 = (2,2,2)
    ratio = nb_cpus
    status = 0
    # First warning
    if status == 0 and load1 >= w1*ratio:
        status = 1
    if status == 0 and load5 >= w5*ratio:
        status = 1
    if status == 0 and load15 >= w15*ratio:
        status = 1
    # Then critical
    if load1 >= c1*ratio:
        status = 2
    if load5 >= c5*ratio:
        status = 2
    if load15 >= c15*ratio:
        status = 2
        
    perfdata = ''
    perfdata += ' load1=%.2f;%.2f;%.2f;;' % (load1, w1*ratio, c1*ratio)
    perfdata += ' load5=%.2f;%.2f;%.2f;;' % (load5, w5*ratio, c5*ratio)
    perfdata += ' load15=%.2f;%.2f;%.2f;;' % (load15, w15*ratio, c15*ratio)
    s_load = '%.2f,%.2f,%.2f' % (load1, load5, load15)
    
    if status == 2:
        return True, "Critical: load average is too high %s | %s" % (s_load, perfdata)

    if status == 1:
        return True, "Warning: load average is too high %s | %s" % (s_load, perfdata)
        
    return False, []
  
def get_uptime():
    stdin, stdout, stderr = exec_command('cat /proc/uptime')
    uptime =  float(stdout[0].split()[0])/3600/24
    if uptime < 1.5:
       return True, u"近期发生重启,运行时长 %s 天." % uptime
    else:
       return False, []

def get_defunct():
    stdin, stdout, stderr = exec_command('ps -ef | grep defunct | grep -v grep | wc -l')
    defunct_count =  int(stdout[0])
    if defunct_count > 5:
       return True, u"发现 %s 个僵尸进程" % defunct_count
    else:
       return False, []
   
def get_df():
    #文件系统使用率大于78%
    raw = r""" df -hP|grep -v loop|awk 'NR>1 && int($5) > 78' """
    stdin, stdout, stderr = exec_command(raw)

    if len(stdout) > 0 :
        return True, "\n".join(stdout) 
    else :
        return False, []
    

def get_df_inode():
    #INODE使用率大于50%
    raw = r""" df -hiP|grep -v loop|awk 'NR>1 && int($5) > 50' """
    stdin, stdout, stderr = exec_command(raw)
    
    if len(stdout) > 0 :
        return True, "\n".join(stdout) 
    else :
        return False, []

    
def get_fs():
    #只读文件系统
    # We are looking for such lines:
    #/dev/sda5 /media/ntfs fuseblk rw,nosuid,nodev,noexec,relatime,user_id=0,group_id=0,default_permissions,allow_other,blksize=4096 0 0
    #/dev/sdb1 /media/bigdata ext3 rw,relatime,errors=continue,barrier=1,data=ordered 0 0

    # Beware of the export!
    stdin, stdout, stderr = exec_command('export LC_LANG=C && unset LANG && grep ^/dev < /proc/mounts |grep -v loop')

    bad_fs = []
    lines = [line for line in stdout]
    # Let's parse al of this
    for line in lines:
        line = line.strip()
        if not line:
            continue
        tmp = line.split(' ')
        opts = tmp[3]
        if 'ro' in opts.split(',') :
            name = tmp[1]
            bad_fs.append(name)
    if len(bad_fs) > 0 :
        return True, "some filesystem are ro.\n" + "\n".join(bad_fs) 
    else :
        return False, []

    
def get_meminfo():
    #内存使用率大于80%
    # We are looking for a line like with value's unit forced to [KB]
    # mem: 2064856    1736636     328220          0     142880     413184
    #      TOTAL      USED        FREE          SHARED  BUF        CACHED
    stdin, stdout, stderr = exec_command('LC_ALL=C free -k')
    total = used = free = shared = buffed = cached = available = 0
    redhat7 = 0
    for line in stdout:
        line = line.strip()
        if 'available' in line:
            redhat7 = 1
        if line.startswith('Mem') and redhat7 == 0:
            tmp = line.split(':')
            # We will have a [2064856, 1736636, 328220, 0, 142880, 413184]
            print tmp
            total, used, free, shared, buffed, cached = (int(v) for v in  tmp[1].split(' ') if v)

        if line.startswith('Mem') and redhat7 == 1:
            tmp = line.split(':')
            print tmp
            total, used, free, shared, buffed, available = (int(v) for v in  tmp[1].split(' ') if v)
        
        if line.startswith('Swap'):
            # We will have a [4385148          0   14385148]
            tmp = line.split(':')
            swap_total, swap_used, swap_free = (int(v) for v in  tmp[1].split(' ') if v)
   
    # Maybe we failed at getting data
    if total == 0:
        print "Error : cannot fetch memory values from host"
        sys.exit(2)
    # Ok analyse data
    if redhat7 == 0:
       pct_used = 100 * float(used - buffed - cached) / total
       pct_used = int(pct_used)
    elif redhat7 == 1:
       pct_used = 100 - 100 * float(available) / total
       pct_used = int(pct_used)
    print "pct_used=%s used=%s buffed=%s cached=%s total=%s available=%s" % (pct_used,used,buffed,cached,total,available)
    if pct_used > 80:
       return True,"memory use %s%%" % pct_used
    else:
       return False,[]

def get_tcp_states():
    #TIME_WAIT连接过多
    # We are looking for a line like 
    #0.19 0.17 0.15 1/616 3634 4
    # l1  l5   l15  _     _    nb_cpus
    raw = r"""cat /proc/net/tcp /proc/net/tcp6 2>/dev/null | awk ' /:/ { c[$4]++; } END { for (x in c) { print x, c[x]; } }'"""
    stdin, stdout, stderr = exec_command(raw)
    states = {}
    for line in stdout:
        line = line.strip()
        if not line:
            continue
        state, nb = tuple(line.split(' '))
        states[state] = int(nb)

    # Thanks the "/proc and /sys" book :)
    mapping = {'ESTABLISHED':'01', 'SYN_SENT':'02', 'SYN_RECV':'03', 'FIN_WAIT1':'04', 'FIN_WAIT2':'05',
               'TIME_WAIT':'06', 'CLOSE':'07', 'CLOSE_WAIT':'08', 'LAST_ACK':'09', 'LISTEN':'0A', 'CLOSING':'0B'}
    perfdata = []
    res = False
    for (k,v) in mapping.iteritems():
        # Try to get by the state ID, if none, get 0 instead
        nb = states.get(v, 0)
        perfdata.append( '%s=%d' % (k, nb) )
    #数据已获取，还未确定判断逻辑    
    if res :
       return True,"%s" % ' '.join(perfdata)
    else:
       return False,[]

def get_sshd_pam():
    #sshd_config 和sshd文件是否启用pam
    raw = r""" ls -rlt $(ps -ef|grep sbin/sshd|grep -v grep|head -1 |  awk '{print $8}')  | awk '{print $9,$11}' """
    stdin, stdout, stderr = exec_command(raw)
    if not stdout:
       return False,[]
    sshd_stdout = stdout[0]
    
    raw = r""" ldd $(ps -ef|grep sbin/sshd|grep -v grep|head -1 |  awk '{print $8}') | grep libpam """
    stdin, stdout, stderr = exec_command(raw)
    libpam = stdout[0]
    
    if libpam:
       if len(sshd_stdout.split()) == 2:
          sshd = sshd_stdout.split()[1]
          sshd_config = sshd.split("sbin")[0]+"etc/sshd_config" 
       else:
          sshd = sshd_stdout.split()[0]
          sshd_config = "/etc/ssh/sshd_config"
       
       raw = r""" cat %s |grep -i usepam|grep -v '#'|tail -1 """  % sshd_config
       stdin, stdout, stderr = exec_command(raw)
       if stdout and  "yes" in stdout[0].lower():
         usepam = stdout
         return False, []
       else:
         return True, u"%s的UsePam参数未打开" % (sshd_config)
    else:
       return True, u"/usr/sbin/sshd的libpam未加载" 

def get_hwclock():
    #检查date和hwclock硬件时钟差，超过100秒告警
    raw = r""" dmidecode -s system-product-name """
    stdin, stdout, stderr = exec_command(raw)
    if stdout:
       if "OpenStack" in stdout[0] or "VMware" in stdout[0]:
          return False, []

    raw = r""" hwclock  """
    stdin, stdout, stderr = exec_command(raw)
    if not stdout:
       return False, []

    if "CST" in stdout[0]:
        hwclock_str = stdout[0].split("CST")[0].strip()
        hwclock_datetime = datetime.datetime.strptime(hwclock_str, '%a %d %b %Y %I:%M:%S %p')
    else:
        hwclock_str = stdout[0].split(".")[0].strip()
        hwclock_datetime = datetime.datetime.strptime(hwclock_str, '%Y-%m-%d %H:%M:%S')
    now_time = datetime.datetime.now()
    if (now_time-hwclock_datetime).days < 0 :
       diff = (hwclock_datetime-now_time).seconds
    else:
       diff = (now_time-hwclock_datetime).seconds
    if abs(diff) > 100 :
        return True, u"hwclock and date time not same, diff:%s seconds" % diff
    else :
        return False, []

def get_sysstat():
    #判断性能监控工具sysstat是否安装并启用
    stdin, stdout, stderr = exec_command('rpm -q sysstat')
    if stdout and  "not installed" in stdout[0]:
       return True, u"sysstat监控组件未安装."
    stdin, stdout, stderr = exec_command('systemctl status sysstat |grep inactive')
    if stdout :
       return True, u"sysstat监控组件未运行."
    else:
       return False, []

if __name__ == '__main__':
    """
    alarm struct as below
    {
    'inode': {'alarm_text': [], 'has_alarm': False}, 
    'filesystem': {'alarm_text': [], 'has_alarm': False}, 
    'average_load': {'alarm_text': [], 'has_alarm': False}, 
    'tcp_status': {'alarm_text': [], 'has_alarm': False},
    'memory': {'alarm_text': [], 'has_alarm': False},
    'ro_filesystem': {'alarm_text': [], 'has_alarm': False},
    'messages': {'alarm_text': [], 'has_alarm': False},
    'ntp': {'alarm_text': [], 'has_alarm': False},
    }
    
    """
    output = { }
    _ret,alarm_text = get_load()
    if _ret:
       output["average_load"] = {}
       output["average_load"].update(has_alarm=_ret, alarm_text=alarm_text)

    ####文件系统使用率检查###
    _ret,alarm_text =  get_df()
    if _ret:
         output["filesystem"] = {}
         output["filesystem"].update(has_alarm=_ret, alarm_text=alarm_text)

    ####文件系统INODE使用率检查###
    _ret,alarm_text =  get_df_inode()
    if _ret:
        output["inode"] = {}
        output["inode"].update(has_alarm=_ret, alarm_text=alarm_text)
        
    ####内存使用率检查###
    _ret,alarm_text = get_meminfo()
    if _ret:
        output["memory"] = {}
        output["memory"].update(has_alarm=_ret, alarm_text=alarm_text)

    ####只读文件系统检查###
    _ret,alarm_text =  get_fs()
    if _ret:
        output["ro_filesystem"] = {}
        output["ro_filesystem"].update(has_alarm=_ret, alarm_text=alarm_text)

    #### TCP连接状态检查 ###
    _ret,alarm_text = get_tcp_states()
    if _ret:
        output["tcp_status"] = {}
        output["tcp_status"].update(has_alarm=_ret, alarm_text=alarm_text)
    

    #### 启动时间检查 ###
    _ret,alarm_text = get_uptime()
    if _ret:
        output["uptime"] = {}
        output["uptime"].update(has_alarm=_ret, alarm_text=alarm_text)

    #### defunct检查 ###
    _ret,alarm_text = get_defunct()
    if _ret:
        output["defunct"] = {}
        output["defunct"].update(has_alarm=_ret, alarm_text=alarm_text)

    #### ntp检查 ###
    _ret,alarm_text = get_ntp_status()
    if _ret:
        output["ntp"] = {}
        output["ntp"].update(has_alarm=_ret, alarm_text=alarm_text)

    #### messages检查 ###
    _ret,alarm_text = get_message_status()
    if _ret:
        output["messages"] = {}
        output["messages"].update(has_alarm=_ret, alarm_text=alarm_text)

    #### pid_max 检查###
    _ret,alarm_text = get_pidmax()
    if _ret:
        output["pidmax"] = {}
        output["pidmax"].update(has_alarm=_ret, alarm_text=alarm_text)

    #### sshd_pam 检查###
    _ret,alarm_text = get_sshd_pam()
    if _ret:
        output["sshd_pam"] = {}
        output["sshd_pam"].update(has_alarm=_ret, alarm_text=alarm_text)

    #### hwclock 时钟检查###
    _ret,alarm_text = get_hwclock()
    if _ret:
        output["hwclock"] = {}
        output["hwclock"].update(has_alarm=_ret, alarm_text=alarm_text)

    #### sysstat检查###
    _ret,alarm_text = get_sysstat()
    if _ret:
        output["get_sysstat"] = {}
        output["get_sysstat"].update(has_alarm=_ret, alarm_text=alarm_text)

    #### user_pid_used 检查###
    _ret,alarm_text = get_user_pid_used()
    if _ret:
        output["get_user_pid_used"] = {}
        output["get_user_pid_used"].update(has_alarm=_ret, alarm_text=alarm_text)

    print output
