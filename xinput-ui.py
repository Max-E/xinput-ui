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

INVALID_ID = -2
FLOATING_ID = -1

def run_command (command):
    p = subprocess.Popen(command,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    return iter(p.stdout.readline, b'')

# Strip all the extra Unicode characters "xinput list" likes to output
def mystrip (string):
    return string.strip(str_whitespace+'\xe2\x8e\xa1\xe2\x8e\x9c\xe2\x86\xb3\xe2\x8e\xa3\x88\xbc')

def device_sort (device_set):
    return sorted(device_set, key = operator.attrgetter ('self_id'))

# These device classes must all have a public "name" attribute

class MasterDevice: # virtual device
    
    def __init__ (self, name):
        self.name = name
        self.children = set()
        self.self_id = self.pointer_id = self.keyboard_id = INVALID_ID
    
    def set_pointer_id (self, pointer_id):
        self.pointer_id = pointer_id
        self.self_id = pointer_id # for device_sort
    
    def set_keyboard_id (self, keyboard_id):
        self.keyboard_id = keyboard_id
    
    def add_slave (self, slave_id, slave_name):
        assert self.self_id != INVALID_ID
        assert self.pointer_id != INVALID_ID
        assert self.keyboard_id != INVALID_ID
        self.children.add (SlaveDevice (self, slave_id, slave_name))

class SlaveDevice: # real physical hardware device
    
    def __init__ (self, parent, self_id, name):
        self.self_id = self_id
        self.name = name
        self.parent = parent
    
class PendingDevice: # virtual device which is pending creation
    
    def __init__ (self, name):
        self.name = name

# Reads the raw output of "xinput list" and parses it somewhat
def read_raw_device_data ():
    
    ret = {}
    
    for line in run_command (["/usr/bin/env", "xinput", "list"]):
        
        raw_device = [mystrip(field) for field in line.split ('\t')]
        raw_class_data = [field.strip('()') for field in raw_device[2][1:-1].split()]
        
        device_self_id = int (raw_device[1].split('=')[1])
        device_name = raw_device[0]
        
        # filter out XTEST devices
        if device_name.find ("XTEST") == -1:
            ret.update ({device_self_id: [device_name, raw_class_data]})
    
    return ret

# Returns a list of MasterDevice objects, each of which may be populated with
# SlaveDevice objects.
def get_device_status ():
    
    unsorted_devices = read_raw_device_data ()
    
    all_masters = {}
    # same as all_masters but with duplicate entries for keyboard device IDs.
    all_master_aliases = {} 
    
    # initialize master devices
    
    device = MasterDevice ("Unattached Devices")
    device.set_pointer_id (FLOATING_ID)
    device.set_keyboard_id (FLOATING_ID)
    all_master_aliases.update ({FLOATING_ID: device})
    all_masters.update ({FLOATING_ID: device})

    for device_id, rawdevice in unsorted_devices.iteritems():
        if rawdevice[1][0] != 'master' or rawdevice[1][1] != 'pointer':
            continue
        device = MasterDevice (rawdevice[0])
        device.set_pointer_id (device_id)
        all_master_aliases.update ({device_id: device})
        all_masters.update ({device_id: device})
    
    for device_id, rawdevice in unsorted_devices.iteritems ():
        if rawdevice[1][0] != 'master' or rawdevice[1][1] != 'keyboard':
            continue
        device = all_master_aliases[int(rawdevice[1][2])]
        device.set_keyboard_id (device_id)
        all_master_aliases.update ({device_id: device})
    
    # initialize slave devices and attach them to their parent master devices
    
    for device_id, rawdevice in unsorted_devices.iteritems ():
        if rawdevice[1][0] == 'master':
            continue 
        master_id = None
        if rawdevice[1][0] == 'floating':
            master_id = FLOATING_ID
        else:
            master_id = int(rawdevice[1][2])
        all_master_aliases[master_id].add_slave (device_id, rawdevice[0])
    
    return all_masters

class FloatingSlaveContext(wx.Menu):
    
    def __init__ (self, window, device, deviceparent):
        
        super(FloatingSlaveContext, self).__init__()
        
        self.window = window
        self.device = device
        self.deviceparent = deviceparent
        
        if self.device.parent != self.deviceparent and self.device.parent not in self.window.all_deletions:
            self.undo_detach = wx.MenuItem(self, wx.NewId(), 'Cancel detatch '+self.device.name)
            self.AppendItem (self.undo_detach)
            self.Bind(wx.EVT_MENU, self.OnUndoDetach, self.undo_detach)
    
    def OnUndoDetach (self, evt):
        
        self.window.MoveDevice (self.device, self.device.parent)

class AttachedSlaveContext(wx.Menu):
    
    def __init__ (self, window, device, deviceparent):
        
        super(AttachedSlaveContext, self).__init__()
        
        self.window = window
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
        
        self.window.MoveDevice (self.device, self.device.parent)
    
    def OnDetach (self, evt):
        
        target_device = self.window.UI.master_devices[FLOATING_ID]
        self.window.MoveDevice (self.device, target_device)
    
    def OnDeleteButton (self, evt):
        
        self.OnDetach (evt)

class MasterDeviceContext(wx.Menu):
    
    def __init__ (self, window, device):
        
        super(MasterDeviceContext, self).__init__()
        
        self.window = window
        self.device_menuitem = self.window.tree.all_devices[device]
        self.device = device
        
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
        
        target_device = self.window.UI.master_devices[FLOATING_ID]
        
        while self.window.tree.ItemHasChildren (self.device_menuitem):
            child_menuitem, unused_cookie = self.window.tree.GetFirstChild(self.device_menuitem)
            child_device = self.window.tree.GetItemPyData(child_menuitem)
            self.window.MoveDevice (child_device, target_device)
    
    def OnDelete (self, evt):
        
        self.OnDetachAll (evt)
        
        title = self.window.tree.GetItemText (self.device_menuitem)
        self.window.tree.SetItemText (self.device_menuitem, title + " (deleted)")
        self.window.all_deletions.add (self.device)
        
        self.window.RefreshCommandList ()
    
    def OnDeleteButton (self, evt):
        
        self.OnDelete (evt)
    
    def OnReset (self, evt):
        
        # First undo any devices that have been moved to this master 
        
        children_to_move = set()
        
        nc = self.window.tree.GetChildrenCount(self.device_menuitem, 0)
        child_menuitem, cookie = self.window.tree.GetFirstChild(self.device_menuitem)
        for i in xrange(nc):
            child_device = self.window.tree.GetItemPyData(child_menuitem)
            if child_device.parent != self.device:
                children_to_move.add (child_device)
            child_menuitem, cookie = self.window.tree.GetNextChild(self.device_menuitem, cookie)
        
        for child_device in children_to_move:
            self.window.MoveDevice (child_device, child_device.parent)
        
        # Now undo any devices that have been moved away from this master
        
        for child_device in self.device.children:
            self.window.MoveDevice (child_device, self.device)
    
    def OnUndoDelete (self, evt):
        
        self.window.all_deletions.remove (self.device)
        self.window.tree.SetItemText (self.device_menuitem, self.device.name)
        
        self.window.RefreshCommandList ()

class PendingMasterContext(wx.Menu):
    
    def __init__ (self, window, device):
        
        super(PendingMasterContext, self).__init__()
        
        self.window = window
        self.device = device
        
        self.cancel = wx.MenuItem (self, wx.NewId(), 'Cancel create pointer '+self.device.name)
        self.AppendItem (self.cancel)
        self.Bind (wx.EVT_MENU, self.OnCancel, self.cancel)
        
    def OnCancel (self, evt):
        
        self.window.all_creations.remove (self.device)
        self.window.tree.Delete (self.device)
        
        self.window.RefreshCommandList ()

class DeviceTree (wx.gizmos.TreeListCtrl):
    
    def __init__ (self, window, parent):
        
        self.window = window
        self.panel = wx.Panel (parent)
        
        self.label = wx.StaticBox (self.panel, label = "Devices:")
        self.sizer = wx.StaticBoxSizer (self.label, wx.VERTICAL)
        
        super (DeviceTree, self).__init__(self.panel, style = wx.TR_HIDE_ROOT | wx.TR_DEFAULT_STYLE | wx.SUNKEN_BORDER)
        
        self.AddColumn ("Name", 350)
        self.AddColumn ("ID", 30)
        self.root = self.AddRoot ("Pointers")
        self.sizer.Add(self, flag = wx.EXPAND, proportion = 1)
        
        self.panel.SetMinSize ((-1, 75))
        
        self.panel.SetSizer (self.sizer)
        
        self.Bind (wx.EVT_TREE_BEGIN_DRAG, self.OnBeginDrag)
        self.Bind (wx.EVT_TREE_END_DRAG, self.OnEndDrag)
        self.Bind (wx.EVT_TREE_ITEM_RIGHT_CLICK, self.OnRightClick)
        
        self.Bind (wx.EVT_TREE_SEL_CHANGED, self.OnSelectItem)
        
        self.all_devices = {}
        
        self.selection_context = None
    
    def addMaster (self, device):
    
        menudev = self.AppendItem (self.root, device.name)
        self.SetItemPyData (menudev, device)
        
        for slave in device_sort(device.children):
            it = self.AppendItem (menudev, slave.name)
            self.SetItemText (it, str(slave.self_id), 1)
            self.SetItemPyData (it, slave) 
        
        self.Expand (menudev)
    
    def SetItemPyData (self, it, data):
        
        super (DeviceTree, self).SetItemPyData(it, data)
        
        self.all_devices.update ({data: it})
    
    def Delete (self, it, *args, **kwargs):
        
        # So "it" can be a menu item or a device object
        if it in self.all_devices:
            it = self.all_devices[it]
        
        super (DeviceTree, self).Delete (it, *args, **kwargs)
        
        data = self.GetItemPyData (it)
        if data != None:
            self.all_devices.pop (data)
    
    def DeleteAllItems (self, *args, **kwargs):
        
        super (DeviceTree, self).DeleteAllItems (*args, **kwargs)
        
        self.root = self.AddRoot ("Pointers")
        self.all_devices = {}
    
    def OnBeginDrag (self, evt):
        it = evt.GetItem ()
        self.dragItem = None
        if self.GetItemPyData(it).__class__ != SlaveDevice:
            return
        self.dragItem = it
        evt.Allow ()
    
    def FindListEntryParentDevice (self, listitem):
        if self.GetItemPyData(listitem).__class__ == SlaveDevice:
            listitem = self.GetItemParent (listitem)
        return self.GetItemPyData(listitem)
    
    def OnEndDrag (self, evt):
    
        if evt.GetItem ().IsOk ():
            target_menuitem = evt.GetItem ()
        else:
            return
        
        source_menuitem = self.dragItem
        
        if source_menuitem == None:
            return
        
        sourcemaster_device = self.FindListEntryParentDevice (source_menuitem)
        target_device = self.FindListEntryParentDevice (target_menuitem)
        source_device = self.GetItemPyData(source_menuitem)
        
        if sourcemaster_device == target_device:
            return
        
        if target_device in self.window.all_creations:
            wx.MessageBox (
                'Cannot add input devices to a pending pointer! '+
                'Hit "Apply" first to finish creating pointer "'+
                target_device.name+'"', 'Error', wx.OK | wx.ICON_EXCLAMATION
            )
            return
        
        if target_device in self.window.all_deletions:
            wx.MessageBox (
                'Pointer "'+target_device.name+'" is pending deletion! '+
                'To cancel deletion of this pointer, right-click it and '+
                'select "Cancel delete."', 'Error', wx.OK | wx.ICON_EXCLAMATION
            )
            return 
        
        self.window.MoveDevice (source_device, target_device)
    
    def OnSelectItem (self, evt):
        
        self.selection_context = None
        
        if evt.GetItem ().IsOk ():
            target = evt.GetItem ()
        else:
            self.selection_context = None
            self.window.toolbar.button_del.Enable (False)
            return
        
        target_device = self.GetItemPyData(target)
        targetparent_device = self.FindListEntryParentDevice (target)
        
        if targetparent_device in self.window.all_creations:
            self.selection_context = PendingMasterContext (self.window, target_device)
        elif targetparent_device == None:
            pass
        elif targetparent_device.self_id == FLOATING_ID:
            if target_device == targetparent_device:
                pass
            else:
                self.selection_context = FloatingSlaveContext (self.window, target_device, targetparent_device)
        else:
            if target_device == targetparent_device:
                self.selection_context = MasterDeviceContext (self.window, target_device)
            else:
                self.selection_context = AttachedSlaveContext (self.window, target_device, targetparent_device)
        
        if target_device == None or targetparent_device.self_id == FLOATING_ID:
            self.window.toolbar.button_del.Enable (False)
        else:
            self.window.toolbar.button_del.Enable (True)
        
    def OnRightClick (self, evt):
        
        if evt.GetItem ().IsOk ():
            target = evt.GetItem ()
        else:
            return
        
        self.SelectItem (target)
        
        if self.selection_context != None:
            self.PopupMenu (self.selection_context)

# The main tooolbar.
class MainBar (wx.Panel):
    
    def __init__ (self, parent):
        
        self.parent = parent
        
        super (MainBar, self).__init__(parent.panel)
        
        self.sizer = wx.BoxSizer (wx.HORIZONTAL)
        
        self.button_refresh = wx.Button (self, label='Refresh', id = wx.ID_REFRESH)
        self.sizer.Add (self.button_refresh)
        self.Bind (wx.EVT_BUTTON, self.parent.UI.refreshDevices, self.button_refresh)
        
        self.button_apply = wx.Button (self, label='Apply', id = wx.ID_APPLY)
        self.button_apply.Enable (False)
        self.sizer.Add (self.button_apply)
        self.Bind (wx.EVT_BUTTON, self.parent.RunCommands, self.button_apply)
        
        self.button_new = wx.Button (self, label='Add', id = wx.ID_ADD)
        self.sizer.Add (self.button_new)
        self.Bind (wx.EVT_BUTTON, self.parent.OnNewMasterStart, self.button_new)
        
        self.button_del = wx.Button (self, label='Remove', id = wx.ID_REMOVE)
        self.button_del.Enable (False)
        self.sizer.Add (self.button_del)
        self.Bind (wx.EVT_BUTTON, self.parent.OnDelete, self.button_del)
        
        self.SetSizer (self.sizer)

# The toolbar that appears when you click on "Add." It has a text field for
# editing the name of the master pointer to create, as well as "OK" and 
# "Cancel" buttons.
class NewMasterBar (wx.Panel):
    
    def __init__ (self, parent):
        
        self.parent = parent
        
        super (NewMasterBar, self).__init__(parent.panel)
        
        self.sizer = wx.BoxSizer (wx.HORIZONTAL)
        
        self.label = wx.StaticText (self, label = "Name:")
        self.sizer.Add (self.label, flag = wx.ALIGN_CENTER)
        
        self.input = wx.TextCtrl (self, style = wx.TE_PROCESS_ENTER)
        self.sizer.Add (self.input, flag = wx.EXPAND, proportion = 1)
        self.Bind (wx.EVT_TEXT_ENTER, self.parent.OnNewMasterDone, self.input)
        
        self.button_confirm = wx.Button (self, label='OK', style = wx.BU_EXACTFIT, id = wx.ID_OK)
        self.sizer.Add (self.button_confirm, flag = wx.ALIGN_RIGHT)
        self.Bind (wx.EVT_BUTTON, self.parent.OnNewMasterDone, self.button_confirm)
        
        self.button_cancel = wx.Button (self, label='Cancel', style = wx.BU_EXACTFIT, id = wx.ID_CANCEL)
        self.sizer.Add (self.button_cancel, flag = wx.ALIGN_RIGHT)
        self.Bind (wx.EVT_BUTTON, self.OnCancel, self.button_cancel)
        
        self.SetSizer (self.sizer)
    
    def Show (self):
    
        self.parent.Show (self, True, True)
        
        self.input.SetValue ("New Pointer")
        self.input.SetSelection (0, -1)
        self.input.SetFocus()
        
        self.parent.Layout ()
    
    def Hide (self):
    
        self.parent.Show (self, False, True)
        self.parent.Layout ()
    
    def OnCancel (self, evt):
        self.Hide ()
    
    def GetValue (self):
        return self.input.GetValue ()

# Used for tracking and displaying the "xinput" commands that will apply
# whatever changes are pending.
class CommandList (wx.ListCtrl):
    
    def __init__ (self, parent):
        
        self.panel = wx.Panel (parent)
        
        self.label = wx.StaticBox (self.panel, label = "Pending Commands:")
        self.panelsizer = wx.StaticBoxSizer (self.label, wx.VERTICAL)
        
        super (CommandList, self).__init__(self.panel, style = wx.LC_REPORT | wx.SUNKEN_BORDER | wx.LC_NO_HEADER)
        self.InsertColumn (0, "Commands", width = 250)
        self.panelsizer.Add (self, flag = wx.EXPAND, proportion = 1)
        
        self.panel.SetMinSize ((-1, 50))
        
        self.panel.SetSizer (self.panelsizer)

# FIXME god object
class MainColumn (wx.BoxSizer):
    
    def __init__ (self, UI, panel):
        
        self.panel = panel
        self.UI = UI
        
        super (MainColumn, self).__init__(wx.VERTICAL)
        
        self.toolbar = MainBar (self)
        self.Add (self.toolbar, flag = wx.ALIGN_TOP)
        
        self.createmaster_panel = NewMasterBar (self)
        self.Add (self.createmaster_panel, proportion = 0, flag = wx.ALIGN_TOP | wx.EXPAND)
        self.createmaster_panel.Hide ()
        
        self.splitter = wx.SplitterWindow (self.panel, -1)
        
        self.cmdlist = CommandList (self.splitter)
        self.tree = DeviceTree (self, self.splitter)
        
        self.splitter.SplitHorizontally (self.tree.panel, self.cmdlist.panel)
        self.splitter.SetSashGravity (1.0)
        self.splitter.SetSashPosition (-100)
        
        self.Add (self.splitter, flag = wx.EXPAND, proportion = 1)
        
        self.panel.SetSizer (self)
        
        self.all_moves = {}
        self.all_deletions = set()
        self.all_creations = set()
        self.all_commands = []
    
    def clearTree (self):
        self.all_moves = {}
        self.all_deletions = set()
        self.all_creations = set()
        self.tree.DeleteAllItems ()
        self.RefreshCommandList ()
    
    def OnDelete (self, evt):
        
        self.tree.selection_context.OnDeleteButton (evt)
    
    def OnNewMasterStart (self, evt):
        
        self.createmaster_panel.Show ()
        
    def OnNewMasterDone (self, evt):
        
        newdevice = PendingDevice (self.createmaster_panel.GetValue ())
        self.createmaster_panel.Hide ()
        
        self.all_creations.add (newdevice)
        
        menudev = self.tree.AppendItem (self.tree.root, newdevice.name+' (pending)' )
        self.tree.SetItemPyData (menudev, newdevice)
        
        self.RefreshCommandList ()
    
    def MoveDevice (self, source_device, target_device):
        
        target_menuitem = self.tree.all_devices[target_device]
        
        self.tree.Delete (source_device)
        
        text = source_device.name
        if source_device.parent != target_device:
            text += ' (move pending)'
        
        new_menuitem = self.tree.AppendItem (target_menuitem, text)
        self.tree.SetItemText (new_menuitem, str(source_device.self_id), 1)
        self.tree.SetItemPyData (new_menuitem, source_device)
        self.tree.Expand (target_menuitem)
        
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
            self.toolbar.button_apply.Enable (True)
        else:
            self.toolbar.button_apply.Enable (False)
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
        
        self.all_commands = []
        
        self.UI.refreshDevices (evt)

class UI (wx.Frame):
    
    def __init__(self, parent, title):
    
        super(UI, self).__init__(parent, title = title, size = (400, 500))
        
        self.SetMinSize ((340, 150))
        
        self.panel = wx.Panel (self)
        self.vbox = MainColumn (self, self.panel)
        
        self.master_devices = get_device_status()
        
        self.initDevices ()
        
        self.Show ()
    
    def initDevices (self):
        
        for device in device_sort(self.master_devices.values()):
            if device.self_id != FLOATING_ID:
                self.vbox.tree.addMaster (device)
        
        # make sure the floating devices list comes last
        self.vbox.tree.addMaster (self.master_devices[FLOATING_ID])
    
    def refreshDevices (self, evt):
        if len (self.vbox.all_commands):
            confirm = wx.MessageDialog (self,
                    'You still have pending changes! These will be lost if '+
                    'you refresh the device list. Refresh anyway?',
                    'Proceed?', wx.YES_NO | wx.ICON_QUESTION
                )
            result = confirm.ShowModal ()
            confirm.Destroy ()
            if result == wx.ID_NO:
                return
        self.master_devices = get_device_status()
        self.vbox.clearTree()
        self.initDevices ()

app = wx.App()
UI(None, title = 'Xinput-UI')
app.MainLoop()

 
