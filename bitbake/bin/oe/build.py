#!usr/bin/python
"""
OpenEmbedded 'Build' implementation

Core code for function execution and task handling in the
OpenEmbedded (http://openembedded.org) build infrastructure.

Copyright: (c) 2003 Chris Larson

Based on functions from the base oe module, Copyright 2003 Holger Schurig
"""

from oe import debug, data, fetch, fatal, error, note, event, mkdirhier
import oe, os, string

# data holds flags and function name for a given task
_task_data = data.init()

# graph represents task interdependencies
_task_graph = oe.digraph()

# stack represents execution order, excepting dependencies
_task_stack = []

# events
class FuncFailed(Exception):
	"""Executed function failed"""

class EventException(Exception):
	"""Exception which is associated with an Event."""

	def __init__(self, msg, event):
		self.event = event

	def getEvent(self):
		return self._event

	def setEvent(self, event):
		self._event = event

	event = property(getEvent, setEvent, None, "event property")

class TaskBase(event.Event):
	"""Base class for task events"""

	def __init__(self, t, d = {}):
		self.task = t
		self.data = d

	def getTask(self):
		return self._task

	def setTask(self, task):
		self._task = task

	task = property(getTask, setTask, None, "task property")

	def getData(self):
		return self._data

	def setData(self, data):
		self._data = data

	data = property(getData, setData, None, "data property")

class TaskStarted(TaskBase):
	"""Task execution started"""
	
class TaskSucceeded(TaskBase):
	"""Task execution completed"""

class TaskFailed(TaskBase):
	"""Task execution failed"""

class InvalidTask(TaskBase):
	"""Invalid Task"""

# functions

def init(data):
	global _task_data, _task_graph, _task_stack
	_task_data = data.init()
	_task_graph = oe.digraph()
	_task_stack = []


def exec_func(func, d, dirs = None):
	"""Execute an OE 'function'"""

	if not dirs:
		dirs = string.split(data.getVarFlag(func, 'dirs', d) or "")
	for adir in dirs:
		adir = data.expand(adir, d)
		mkdirhier(adir) 

	if len(dirs) > 0:
		adir = dirs[-1]
	else:
		adir = data.getVar('S', d)

	adir = data.expand(adir, d)

	prevdir = os.getcwd()
	if adir and os.access(adir, os.F_OK):
		os.chdir(adir)

	if data.getVarFlag(func, "python", d):
		exec_func_python(func, d)
	else:
		exec_func_shell(func, d)
	os.chdir(prevdir)

def tmpFunction(d):
	"""Default function for python code blocks"""
	return 1

def exec_func_python(func, d):
	"""Execute a python OE 'function'"""
	body = data.getVar(func, d)
	if not body:
		return
	tmp = "def tmpFunction(d):\n%s" % body
	comp = compile(tmp, "tmpFunction(d)", "exec")
	prevdir = os.getcwd()
	exec(comp)
	os.chdir(prevdir)
	tmpFunction(d)

def exec_func_shell(func, d):
	"""Execute a shell OE 'function' Returns true if execution was successful.

	For this, it creates a bash shell script in the tmp dectory, writes the local
	data into it and finally executes. The output of the shell will end in a log file and stdout.

	Note on directory behavior.  The 'dirs' varflag should contain a list
	of the directories you need created prior to execution.  The last
	item in the list is where we will chdir/cd to.
	"""
	import sys

	deps = data.getVarFlag(func, 'deps', d)
	check = data.getVarFlag(func, 'check', d)
	if check in globals():
		if globals()[check](func, deps):
			return

	global logfile
	t = data.getVar('T', d)
	if not t:
		return 0
	t = data.expand(t, d)
	mkdirhier(t)
	logfile = "%s/log.%s.%s" % (t, func, str(os.getpid()))
	runfile = "%s/run.%s.%s" % (t, func, str(os.getpid()))

	f = open(runfile, "w")
	f.write("#!/bin/sh -e\n")
	if data.getVar("OEDEBUG", d): f.write("set -x\n")
	data.emit_env(f, d)

	f.write("cd %s\n" % os.getcwd())
	if func: f.write("%s || exit $?\n" % func)
	f.close()
	os.chmod(runfile, 0775)
	if not func:
		error("Function not specified")
		raise FuncFailed()

	# open logs
	si = file('/dev/null', 'r')
	so = file(logfile, 'a')
	se = file(logfile, 'a+', 0)

	# dup the existing fds so we dont lose them
	osi = [os.dup(sys.stdin.fileno()), sys.stdin.fileno()]
	oso = [os.dup(sys.stdout.fileno()), sys.stdout.fileno()]
	ose = [os.dup(sys.stderr.fileno()), sys.stderr.fileno()]

	# replace those fds with our own
	os.dup2(si.fileno(), osi[1])
	os.dup2(so.fileno(), oso[1])
	os.dup2(se.fileno(), ose[1])

	# execute function
	prevdir = os.getcwd()
	ret = os.system('sh -e %s' % runfile)
	os.chdir(prevdir)

	# restore the backups
	os.dup2(osi[0], osi[1])
	os.dup2(oso[0], oso[1])
	os.dup2(ose[0], ose[1])

	# close our logs
	si.close()
	so.close()
	se.close()

	# close the backup fds
	os.close(osi[0])
	os.close(oso[0])
	os.close(ose[0])

	if ret==0:
		if not data.getVar("OEDEBUG"):
			os.remove(runfile)
#			os.remove(logfile)
		return
	else:
		error("function %s failed" % func)
		error("see log in %s" % logfile)
		raise FuncFailed()


_task_cache = []

def exec_task(task, d):
	"""Execute an OE 'task'

	   The primary difference between executing a task versus executing
	   a function is that a task exists in the task digraph, and therefore
	   has dependencies amongst other tasks."""

	# check if the task is in the graph..
	task_graph = data.getVar('_task_graph', d)
	if not task_graph:
		task_graph = oe.digraph()
		data.setVar('_task_graph', task_graph, d)
	task_cache = data.getVar('_task_cache', d)
	if not task_cache:
		task_cache = []
		data.setVar('_task_cache', task_cache, d)
	if not task_graph.hasnode(task):
		raise EventException("", InvalidTask(task, d))

	# check whether this task needs executing..
	if not data.getVarFlag(task, 'force', d):
		if stamp_is_current(task, d):
			return 1

	# follow digraph path up, then execute our way back down
	def execute(graph, item):
		if data.getVarFlag(item, 'task', d):
			if item in task_cache:
				return 1

			if task != item:
				# deeper than toplevel, exec w/ deps
				exec_task(item, d)
				return 1

			try:
				debug(1, "Executing task %s" % item)
				event.fire(TaskStarted(item, d))
				exec_func(item, d)
				event.fire(TaskSucceeded(item, d))
				task_cache.append(item)
			except FuncFailed:
				failedevent = TaskFailed(item, d)
				event.fire(failedevent)
				raise EventException(None, failedevent)

	# execute
	task_graph.walkdown(task, execute)

	# make stamp, or cause event and raise exception
	if not data.getVarFlag(task, 'nostamp', d):
		mkstamp(task, d)


def stamp_is_current(task, d, checkdeps = 1):
	"""Check status of a given task's stamp. returns 0 if it is not current and needs updating."""
	task_graph = data.getVar('_task_graph', d)
	if not task_graph:
		task_graph = oe.digraph()
		data.setVar('_task_graph', task_graph, d)
	stamp = data.getVar('STAMP', d)
	if not stamp:
		return 0
	stampfile = "%s.%s" % (data.expand(stamp, d), task)
	if not os.access(stampfile, os.F_OK):
		return 0

	if checkdeps == 0:
		return 1

	import stat
	tasktime = os.stat(stampfile)[stat.ST_MTIME]

	_deps = []
	def checkStamp(graph, task):
		# check for existance
		if data.getVarFlag(task, 'nostamp', d):
			return 1

		if not stamp_is_current(task, d, 0):
			return 0

		depfile = "%s.%s" % (data.expand(stamp, d), task)
		deptime = os.stat(depfile)[stat.ST_MTIME]
		if deptime > tasktime:
			return 0
		return 1

	return task_graph.walkdown(task, checkStamp)


def md5_is_current(task):
	"""Check if a md5 file for a given task is current""" 


def mkstamp(task, d):
	"""Creates/updates a stamp for a given task"""
	mkdirhier(data.expand('${TMPDIR}/stamps', d));
	stamp = data.getVar('STAMP', d)
	if not stamp:
		return
	stamp = "%s.%s" % (data.expand(stamp, d), task)
	open(stamp, "w+")


def add_task(task, deps, d):
	task_graph = data.getVar('_task_graph', d)
	if not task_graph:
		task_graph = oe.digraph()
		data.setVar('_task_graph', task_graph, d)
	data.setVarFlag(task, 'task', 1, d)
	task_graph.addnode(task, None)
	for dep in deps:
		if not task_graph.hasnode(dep):
			task_graph.addnode(dep, None)
		task_graph.addnode(task, dep)


def remove_task(task, kill, d):
	"""Remove an OE 'task'.

	   If kill is 1, also remove tasks that depend on this task."""

	task_graph = data.getVar('_task_graph', d)
	if not task_graph:
		task_graph = oe.digraph()
		data.setVar('_task_graph', task_graph, d)
	if not task_graph.hasnode(task):
		return

	data.delVarFlag(task, 'task', d)
	ref = 1
	if kill == 1:
		ref = 2
	task_graph.delnode(task, ref)

def task_exists(task, d):
	task_graph = data.getVar('_task_graph', d)
	if not task_graph:
		task_graph = oe.digraph()
		data.setVar('_task_graph', task_graph, d)
	return task_graph.hasnode(task)

def get_task_data():
	return _task_data
