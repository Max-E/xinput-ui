#! /usr/bin/env python2.7

# xinput-ui
# A GUI front-end for the xinput utility, allowing graphical control over 
# X.Org's Multi-Pointer X (MPX) features. Created mainly as a project to learn 
# wxPython. The code is pretty horrible and has been cobbled together from 
# several tutorials.

# Copyright (c) 2013 Max Eliaser
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and/or associated documentation files (the
# "Materials"), to deal in the Materials without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Materials, and to
# permit persons to whom the Materials are furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Materials.
#
# THE MATERIALS ARE PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# MATERIALS OR THE USE OR OTHER DEALINGS IN THE MATERIALS.

# Sources I used:
#  - http://zetcode.com/wxpython/
#  - http://wiki.wxpython.org/

import wx, wx.gizmos
import subprocess
from string import whitespace as str_whitespace
import operator

FLOATING_ID = -1

def run_command (command):
    p = subprocess.Popen(command,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    return iter(p.stdout.readline, b'')

def mystrip (string):
    return string.strip(str_whitespace+'\xe2\x8e\xa1\xe2\x8e\x9c\xe2\x86\xb3\xe2\x8e\xa3\x88\xbc')

def mysort (device_set):
    return sorted(device_set, key = operator.attrgetter ('self_id'))

def generate_unique ():
    return []

class MasterDevice:
    
    def __init__ (self, status, name):
        self.name = name
        self.devices = set()
    
    def set_pointer_id (self, pointer_id):
        self.pointer_id = pointer_id
        self.self_id = pointer_id # for mysort
    
    def set_keyboard_id (self, keyboard_id):
        self.keyboard_id = keyboard_id
    
    def add_device (self, device):
        self.devices.add(device)
    
    def remove_device (self, device):
        self.devices.remove(device)

class SlaveDevice:
    
    def __init__ (self, status, self_id, name):
        self.status = status
        self.self_id = self_id
        self.name = name
        self.parent = None
        self.parent_id = None
    
    def set_parent (self, parent_id):
        if self.parent != None:
            self.parent.remove_device (self)
        self.parent_id = parent_id
        self.parent = self.status.get_device (parent_id)
        self.parent.add_device (self)

class PendingDevice:
    
    def __init__ (self, name):
        self.name = name

class Status:
    
    def __init__ (self, rawstatus):
        self.all_devices = {}
        self.all_masters = set()
        self.init_masters (rawstatus)
        self.init_slaves (rawstatus)
    
    def init_masters (self, rawstatus):
    
        device = MasterDevice (self, "(floating)")
        device.set_pointer_id (FLOATING_ID)
        device.set_keyboard_id (FLOATING_ID)
        self.all_devices.update ({FLOATING_ID: device})
        self.all_masters.add (device)
    
        for device_id, rawdevice in rawstatus.get_all_devices ():
            if rawdevice[1][0] != 'master' or rawdevice[1][1] != 'pointer':
                continue
            device = MasterDevice (self, rawdevice[0])
            device.set_pointer_id (device_id)
            self.all_devices.update ({device_id: device})
            self.all_masters.add (device)
        
        for device_id, rawdevice in rawstatus.get_all_devices ():
            if rawdevice[1][0] != 'master' or rawdevice[1][1] != 'keyboard':
                continue
            device = self.all_devices[int(rawdevice[1][2])]
            device.set_keyboard_id (device_id)
            self.all_devices.update ({device_id: device})
    
    def init_slaves (self, rawstatus):
        for device_id, rawdevice in rawstatus.get_all_devices ():
            if rawdevice[1][0] == 'master':
                continue 
            device = None
            master_id = None
            if rawdevice[1][0] == 'floating':
                master_id = FLOATING_ID
            else:
                master_id = int(rawdevice[1][2])
            device = SlaveDevice (self, device_id, rawdevice[0])
            device.set_parent (master_id)
            self.all_devices.update ({device_id: device})
    
    def get_device (self, device_id):
        return self.all_devices[device_id]

class Rawstatus:
    
    def __init__ (self):
        self.all_devices = {}
        for line in run_command (["/usr/bin/env", "xinput", "list"]):
            self.add_device (line)
    
    def add_device (self, line):
        raw_device = [mystrip(field) for field in line.split ('\t')]
        raw_class_data = [field.strip('()') for field in raw_device[2][1:-1].split()]
        
        device_self_id = int (raw_device[1].split('=')[1])
        device_name = raw_device[0]
        
        if device_name.find ("XTEST") != -1:
            return
        
        self.all_devices.update ({device_self_id: [device_name, raw_class_data]})
    
    def get_all_devices (self):
        return self.all_devices.iteritems()
    
    def Status (self):
        return Status (self)

app = wx.App()

class MyTextDropTarget(wx.TextDropTarget):

    def __init__(self, object):
        wx.TextDropTarget.__init__(self)
        self.object = object

    def OnDropText(self, x, y, data):
        self.object.InsertStringItem(0, data)

class FloatingSlaveContext(wx.Menu):
    
    def __init__ (self, window, device_menuitem, device, deviceparent):
        
        super(FloatingSlaveContext, self).__init__()
        
        self.window = window
        self.device_menuitem = device_menuitem
        self.device = device
        self.deviceparent = deviceparent
        
        if self.device.parent != self.deviceparent and self.device.parent not in self.window.all_deletions:
            self.undo_detach = wx.MenuItem(self, wx.NewId(), 'Cancel detatch '+self.device.name)
            self.AppendItem (self.undo_detach)
            self.Bind(wx.EVT_MENU, self.OnUndoDetach, self.undo_detach)
    
    def OnUndoDetach (self, evt):
        
        self.window.all_moves.pop (self.device, None)
        self.window.RefreshCommandList ()
        
        target_menu_it = self.window.all_masters[self.device.parent]
        source_metadata = self.window.tree.GetItemPyData(self.device_menuitem)
        self.window.MoveMenuItem (self.device_menuitem, target_menu_it, source_metadata)

class AttachedSlaveContext(wx.Menu):
    
    def __init__ (self, window, device_menuitem, device, deviceparent):
        
        super(AttachedSlaveContext, self).__init__()
        
        self.window = window
        self.device_menuitem = device_menuitem
        self.device = device
        self.deviceparent = deviceparent
        
        if self.device.parent != self.deviceparent and self.device.parent not in self.window.all_deletions:
            self.undo_move = wx.MenuItem(self, wx.NewId(), 'Cancel reattach '+self.device.name)
            self.AppendItem (self.undo_move)
            self.Bind(wx.EVT_MENU, self.OnUndoMove, self.undo_move)
        
        if self.device.parent.self_id != FLOATING_ID:
            self.detach = wx.MenuItem (self, wx.NewId(), 'Detach '+self.device.name)
            self.AppendItem (self.detach)
            self.Bind(wx.EVT_MENU, self.OnDetach, self.detach)
    
    def OnUndoMove (self, evt):
        
        self.window.all_moves.pop (self.device, None)
        self.window.RefreshCommandList ()
        
        target_menu_it = self.window.all_masters[self.device.parent]
        source_metadata = self.window.tree.GetItemPyData(self.device_menuitem)
        self.window.MoveMenuItem (self.device_menuitem, target_menu_it, source_metadata)
    
    def OnDetach (self, evt):
        
        target_device = self.window.UI.stats.get_device (FLOATING_ID)
        self.window.all_moves.update ({self.device: target_device})
        self.window.RefreshCommandList ()
        
        target_menu_it = self.window.all_masters[target_device]
        source_metadata = self.window.tree.GetItemPyData(self.device_menuitem)
        self.window.MoveMenuItem (self.device_menuitem, target_menu_it, source_metadata)

class MasterDeviceContext(wx.Menu):
    
    def __init__ (self, window, device_menuitem, device):
        
        super(MasterDeviceContext, self).__init__()
        
        self.window = window
        self.device_menuitem = device_menuitem
        self.device = device
        self.device_metadata = self.window.tree.GetItemPyData(self.device_menuitem)
        
        if self.device in self.window.all_deletions:
            self.undo_delete = wx.MenuItem (self, wx.NewId(), 'Cancel delete '+self.device.name)
            self.AppendItem (self.undo_delete)
            self.Bind (wx.EVT_MENU, self.OnUndoDelete, self.undo_delete)
            return
        
        self.reset = wx.MenuItem (self, wx.NewId(), 'Reset all devices for '+self.device.name)
        self.AppendItem (self.reset)
        self.Bind (wx.EVT_MENU, self.OnReset, self.reset)
        
        self.delete = wx.MenuItem (self, wx.NewId(), 'Delete '+self.device.name)
        self.AppendItem (self.delete)
        self.Bind (wx.EVT_MENU, self.OnDelete, self.delete)
        
        self.detach_all = wx.MenuItem (self, wx.NewId(), 'Detatch all devices from '+self.device.name)
        self.AppendItem (self.detach_all)
        self.Bind (wx.EVT_MENU, self.OnDetachAll, self.detach_all)
    
    def OnDetachAll (self, evt):
        
        target_device = self.window.UI.stats.get_device (FLOATING_ID)
        target_menu_it = self.window.all_masters[target_device]
        
        nc = self.window.tree.GetChildrenCount(self.device_menuitem, 0)
        while self.window.tree.ItemHasChildren (self.device_menuitem):
            child_menuitem, cookie = self.window.tree.GetFirstChild(self.device_menuitem)
            child_metadata = self.window.tree.GetItemPyData(child_menuitem)
            child_device = child_metadata[1]
            if child_device.parent == target_device:
                self.window.all_moves.pop (child_device, NULL)
            else:
                self.window.all_moves.update ({child_device: target_device})
            self.window.MoveMenuItem (child_menuitem, target_menu_it, child_metadata)
        
        self.window.RefreshCommandList ()
    
    def OnDelete (self, evt):
        
        self.OnDetachAll (evt)
        
        title = self.window.tree.GetItemText (self.device_menuitem)
        self.window.tree.SetItemText (self.device_menuitem, title + " (deleted)")
        self.window.all_deletions.add (self.device)
        
        self.window.RefreshCommandList ()
    
    def OnReset (self, evt):
        pass
    
    def OnUndoDelete (self, evt):
        
        self.window.all_deletions.remove (self.device)
        self.window.tree.SetItemText (self.device_menuitem, self.device.name)
        
        self.window.RefreshCommandList ()

class PendingMasterContext(wx.Menu):
    
    def __init__ (self, window, device_menuitem, device):
        
        super(PendingMasterContext, self).__init__()
        
        self.window = window
        self.device_menuitem = device_menuitem
        self.device = device
        
        self.cancel = wx.MenuItem (self, wx.NewId(), 'Undo create pointer '+self.device.name)
        self.AppendItem (self.cancel)
        self.Bind (wx.EVT_MENU, self.OnCancel, self.cancel)
        
    def OnCancel (self, evt):
        
        self.window.all_creations.remove (self.device)
        self.window.tree.Delete (self.device_menuitem)
        
        self.window.RefreshCommandList ()

class MainColumn (wx.BoxSizer):
    
    def __init__ (self, UI, panel):
        
        self.panel = panel
        self.UI = UI
        
        super (MainColumn, self).__init__(wx.VERTICAL)
        
        self.initToolbar ()
        self.initNewMasterName ()
        
        self.splitter = wx.SplitterWindow (self.panel, -1)
        
        self.initTree ()
        self.initCmdList ()
        
        self.splitter.SplitHorizontally (self.treepanel, self.cmdlistpanel)
        self.splitter.SetSashGravity (1.0)
        self.splitter.SetSashPosition (-100)
        
        self.Add (self.splitter, flag = wx.EXPAND, proportion = 1)
        
        self.panel.SetSizer (self)
        
        self.all_masters = {}
        self.all_moves = {}
        self.all_deletions = set()
        self.all_creations = set()
        self.all_commands = []
    
    def initToolbar (self):
        
        self.toolbar_panel = wx.Panel (self.panel)
        self.toolbar = wx.BoxSizer (wx.HORIZONTAL)
        
        self.button_refresh = wx.Button (self.toolbar_panel, label='Refresh', id = wx.ID_REFRESH)
        self.toolbar.Add (self.button_refresh)
        
        self.button_apply = wx.Button (self.toolbar_panel, label='Apply', id = wx.ID_APPLY)
        self.button_apply.Enable (False)
        self.toolbar.Add (self.button_apply)
        self.panel.Bind (wx.EVT_BUTTON, self.RunCommands, self.button_apply)
        
        self.button_new = wx.Button (self.toolbar_panel, label='Add', id = wx.ID_ADD)
        self.toolbar.Add (self.button_new)
        self.panel.Bind (wx.EVT_BUTTON, self.OnNewMasterStart, self.button_new)
        
        self.toolbar_panel.SetSizer (self.toolbar)
        
        self.Add (self.toolbar_panel, flag = wx.ALIGN_TOP)
    
    def initNewMasterName (self):
        
        self.newname_panel = wx.Panel (self.panel)
        self.newname_bar = wx.BoxSizer (wx.HORIZONTAL)
        
        self.newname_label = wx.StaticText (self.newname_panel, label = "Name:")
        self.newname_bar.Add (self.newname_label, flag = wx.ALIGN_CENTER)
        
        self.newname_input = wx.TextCtrl (self.newname_panel, style = wx.TE_PROCESS_ENTER)
        self.newname_bar.Add (self.newname_input, flag = wx.EXPAND, proportion = 1)
        self.panel.Bind (wx.EVT_TEXT_ENTER, self.OnNewMasterEnter, self.newname_input)
        
        self.button_confirm_name = wx.Button (self.newname_panel, label='OK', style = wx.BU_EXACTFIT, id = wx.ID_OK)
        self.newname_bar.Add (self.button_confirm_name, flag = wx.ALIGN_RIGHT)
        self.panel.Bind (wx.EVT_BUTTON, self.OnNewMasterEnter, self.button_confirm_name)
        
        self.button_cancel_name = wx.Button (self.newname_panel, label='Cancel', style = wx.BU_EXACTFIT, id = wx.ID_CANCEL)
        self.newname_bar.Add (self.button_cancel_name, flag = wx.ALIGN_RIGHT)
        self.panel.Bind (wx.EVT_BUTTON, self.OnNewMasterCancel, self.button_cancel_name)
        
        self.newname_panel.SetSizer (self.newname_bar)
        
        self.Add (self.newname_panel, proportion = 0, flag = wx.ALIGN_TOP | wx.EXPAND)
        self.Show (self.newname_panel, False, True)
        
    def showNewMasterName (self):
    
        self.Show (self.newname_panel, True, True)
        
        self.newname_input.SetValue ("New Pointer")
        self.newname_input.SetSelection (0, -1)
        self.newname_input.SetFocus()
        
        self.Layout ()
    
    def hideNewMasterName (self):
    
        self.Show (self.newname_panel, False, True)
        self.Layout ()
    
    def initTree (self):
    
        self.treepanel = wx.Panel (self.splitter)
        self.treelabel = wx.StaticBox (self.treepanel, label = "Devices:")
        self.treepanelsizer = wx.StaticBoxSizer (self.treelabel, wx.VERTICAL)
        
        self.tree = wx.gizmos.TreeListCtrl (self.treepanel, style = wx.TR_HIDE_ROOT | wx.TR_DEFAULT_STYLE | wx.SUNKEN_BORDER)
        self.tree.AddColumn ("Name", 250)
        self.tree.AddColumn ("ID", 30)
        self.root = self.tree.AddRoot ("Pointers")
        self.treepanelsizer.Add(self.tree, flag = wx.EXPAND, proportion = 1)
        
        self.treepanel.SetSizer (self.treepanelsizer)
        
        self.tree.Bind (wx.EVT_TREE_BEGIN_DRAG, self.BeginDrag)
        self.tree.Bind (wx.EVT_TREE_END_DRAG, self.EndDrag)
        self.tree.Bind (wx.EVT_TREE_ITEM_RIGHT_CLICK, self.RightClickTree)
    
    def initCmdList (self):
        self.cmdlistpanel = wx.Panel (self.splitter)
        self.cmdlistlabel = wx.StaticBox (self.cmdlistpanel, label = "Pending Commands:")
        self.cmdlistpanelsizer = wx.StaticBoxSizer (self.cmdlistlabel, wx.VERTICAL)
        
        self.cmdlist = wx.ListCtrl (self.cmdlistpanel, style = wx.LC_REPORT | wx.SUNKEN_BORDER | wx.LC_NO_HEADER)
        self.cmdlist.InsertColumn (0, "Commands", width = 250)
        self.cmdlistpanelsizer.Add (self.cmdlist, flag = wx.EXPAND, proportion = 1)
        
        self.cmdlistpanel.SetSizer (self.cmdlistpanelsizer)
        
    def clearTree (self):
        self.all_masters = {}
        self.all_moves = {}
        self.all_deletions = set()
        self.all_creations = set()
        self.tree.DeleteAllItems ()
        self.root = self.tree.AddRoot ("Pointers")
        self.RefreshCommandList ()
    
    def addMaster (self, device):
    
        menudev = self.tree.AppendItem (self.root, device.name)
        self.tree.SetItemPyData (menudev, ['master', device])
        
        self.all_masters.update ({device: menudev})
        
        for slave in mysort(device.devices):
            it = self.tree.AppendItem (menudev, slave.name)
            self.tree.SetItemText (it, str(slave.self_id), 1)
            self.tree.SetItemPyData (it, ['slave', slave]) 
        
        self.tree.Expand (menudev)
    
    def addFloating (self, device):
        
        menudev = self.tree.AppendItem (self.root, "Unattached Devices")
        self.tree.SetItemPyData (menudev, ['floating', device])
        
        self.all_masters.update ({device: menudev})
        
        for slave in mysort(device.devices):
            it = self.tree.AppendItem (menudev, slave.name)
            self.tree.SetItemText (it, str(slave.self_id), 1)
            self.tree.SetItemPyData (it, ['slave', slave]) 
        
        self.tree.Expand (menudev)
    
    def OnNewMasterStart (self, evt):
        self.showNewMasterName ()
    
    def OnNewMasterEnter (self, evt):
        
        newdevice = PendingDevice (self.newname_input.GetValue ())
        self.hideNewMasterName ()
        
        self.all_creations.add (newdevice)
        
        menudev = self.tree.AppendItem (self.root, newdevice.name+' (pending)' )
        self.tree.SetItemPyData (menudev, ['pending', newdevice])
        
        self.all_masters.update ({newdevice: menudev})
        
        self.RefreshCommandList ()
    
    def OnNewMasterCancel (self, evt):
        self.hideNewMasterName ()
    
    def BeginDrag (self, evt):
        it = evt.GetItem ()
        self.dragItem = None
        if 'slave' not in []+self.tree.GetItemPyData(it):
            return
        self.dragItem = it
        evt.Allow ()
    
    def FindListEntryParentDevice (self, listitem):
        if 'slave' in []+self.tree.GetItemPyData(listitem):
            listitem = self.tree.GetItemParent (listitem)
        return listitem
    
    def EndDrag (self, evt):
    
        if evt.GetItem ().IsOk ():
            target = evt.GetItem ()
        else:
            return
        
        source = self.dragItem
        
        if source == None:
            return
        
        sourcemaster = self.FindListEntryParentDevice (source)
        target = self.FindListEntryParentDevice (target)
        
        target_metadata = self.tree.GetItemPyData(target)
        source_metadata = self.tree.GetItemPyData(source)
        
        if target_metadata[0] == 'pending':
            return #TODO popup
        
        target_device = target_metadata[1]
        source_device = source_metadata[1]
        
        if self.tree.GetItemPyData(sourcemaster)[1] == target_device:
            return
        
        if target_device in self.all_deletions:
            return #TODO popup
        
        target_menu_it = self.all_masters[target_device]
        
        self.MoveMenuItem (source, target_menu_it, source_metadata)
        
        self.DeviceMoved (source_device, target_device)
    
    def MoveMenuItem (self, source_menu_it, target_menu_it, source_metadata):
        
        source_device = source_metadata[1]
        
        new_menu_it = self.tree.AppendItem (target_menu_it, source_device.name)
        self.tree.SetItemText (new_menu_it, str(source_device.self_id), 1)
        self.tree.SetItemPyData (new_menu_it, source_metadata)
        self.tree.Expand (target_menu_it)
        self.tree.Delete (source_menu_it)
    
    def DeviceMoved (self, source_device, target_device):
        
        if source_device.parent == target_device:
            self.all_moves.pop (source_device, None)
        else:
            self.all_moves.update ({source_device: target_device})
        
        self.RefreshCommandList ()
    
    def AddCommand (self, argslist):
        self.all_commands += [argslist]
        self.cmdlist.InsertStringItem (self.cmdlist.GetItemCount(), " ".join (argslist))
    
    def RefreshCommandList (self):
    
        self.cmdlist.DeleteAllItems ()
        self.all_commands = []
        
        if len(self.all_moves) + len(self.all_deletions) + len(self.all_creations):
            self.button_apply.Enable (True)
        else:
            self.button_apply.Enable (False)
            return
        
        for source, dest in self.all_moves.iteritems():
            if dest.self_id == FLOATING_ID:
                if source.parent not in self.all_deletions:
                    self.AddCommand (["xinput", "float", str(source.self_id)])
            else:
                self.AddCommand (["xinput", "reattach", str(source.self_id), str(dest.pointer_id)])
                self.AddCommand (["xinput", "reattach", str(source.self_id), str(dest.keyboard_id)])
        
        for device in self.all_deletions:
            self.AddCommand (["xinput", "remove-master", str(device.self_id)])
        
        for device in self.all_creations:
            self.AddCommand (["xinput", "create-master", device.name])
    
    def RunCommands (self, evt):
        
        for cmd in self.all_commands:
            subprocess.Popen (["/usr/bin/env"] + cmd)
        
        evt = wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, self.button_refresh.GetId())
        wx.PostEvent(self.button_refresh, evt)
    
    def RightClickTree (self, evt):
        
        if evt.GetItem ().IsOk ():
            target = evt.GetItem ()
        else:
            return
            
        self.tree.SelectItem(target)
        
        targetparent = self.FindListEntryParentDevice (target)
        
        target_metadata = self.tree.GetItemPyData(target)
        target_device = target_metadata[1]
        targetparent_metadata = self.tree.GetItemPyData(targetparent)
        targetparent_device = targetparent_metadata[1]
        
        if targetparent_metadata[0] == "floating":
            if target_metadata == targetparent_metadata:
                pass
            else:
                self.tree.PopupMenu (FloatingSlaveContext (self, target, target_device, targetparent_device))
        elif targetparent_metadata[0] == "pending":
            self.tree.PopupMenu (PendingMasterContext (self, target, target_device))
        else:
            if target_metadata == targetparent_metadata:
                self.tree.PopupMenu (MasterDeviceContext (self, target, target_device))
            else:
                self.tree.PopupMenu (AttachedSlaveContext (self, target, target_device, targetparent_device))
    

class UI (wx.Frame):
    
    def __init__(self, parent, title):
    
        super(UI, self).__init__(parent, title = title, size = (320, 500))
        
        self.panel = wx.Panel (self)
        self.vbox = MainColumn (self, self.panel)
        
        self.Bind (wx.EVT_BUTTON, self.refreshDevices, self.vbox.button_refresh)
        
        self.stats = Rawstatus().Status()
        
        self.initDevices ()
        
        self.Show ()
    
    def initDevices (self):
        
        for device in mysort(self.stats.all_masters):
            if device.name != '(floating)':
                self.vbox.addMaster (device)
        
        self.vbox.addFloating (self.stats.all_devices[FLOATING_ID])
    
    def refreshDevices (self, evt):
        self.stats = Rawstatus().Status()
        self.vbox.clearTree()
        self.initDevices ()
        
UI(None, title = 'Xinput-UI')

app.MainLoop()

 
