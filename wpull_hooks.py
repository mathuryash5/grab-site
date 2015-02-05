import re
import os
import json
import pprint
from urllib.request import urlopen
from ignoracle import Ignoracle, parameterize_record_info

cache = {}
def getPatternsForIgnoreSet(name):
	assert name != "", name
	if name in cache:
		return cache[name]
	print("Fetching ArchiveBot/master/db/ignore_patterns/%s.json" % name)
	cache[name] = json.loads(urlopen("https://raw.githubusercontent.com/ArchiveTeam/ArchiveBot/master/db/ignore_patterns/%s.json" % name).read().decode("utf-8"))["patterns"]
	return cache[name]

hook_settings_dir = os.environ['HOOK_SETTINGS_DIR']

ignoracle = Ignoracle()

def mtime(f):
	return os.stat(f).st_mtime

class FileChangedWatcher(object):
	def __init__(self, fname):
		self.fname = fname
		self.last_mtime = mtime(fname)

	def has_changed(self):
		now_mtime = mtime(self.fname)
		changed = mtime(self.fname) != self.last_mtime
		self.last_mtime = now_mtime
		return changed


ignore_sets_w = FileChangedWatcher(os.path.join(hook_settings_dir, "ignore_sets"))
ignores_w = FileChangedWatcher(os.path.join(hook_settings_dir, "ignores"))

def update_ignoracle():
	with open(os.path.join(hook_settings_dir, "ignore_sets"), "r") as f:
		ignore_sets = f.read().strip("\r\n\t ,").split(',')

	with open(os.path.join(hook_settings_dir, "ignores"), "r") as f:
		ignores = set(ig for ig in f.read().strip("\r\n").split('\n') if ig != "")

	for igset in ignore_sets:
		ignores.update(getPatternsForIgnoreSet(igset))

	print("Using these %d ignores:" % len(ignores))
	pprint.pprint(ignores)

	ignoracle.set_patterns(ignores)

update_ignoracle()


def ignore_url_p(url, record_info):
	'''
	Returns whether a URL should be ignored.
	'''
	parameters = parameterize_record_info(record_info)
	return ignoracle.ignores(url, **parameters)


def accept_url(url_info, record_info, verdict, reasons):
	if ignore_sets_w.has_changed() or ignores_w.has_changed():
		update_ignoracle()

	url = url_info['url']

	if url.startswith('data:'):
		# data: URLs aren't something you can grab, so drop them to avoid ignore
		# checking and ignore logging.
		return False

	pattern = ignore_url_p(url, record_info)
	if pattern:
		print("IGNOR %s by %s" % (url, pattern))
		return False

	# If we get here, none of our ignores apply.	Return the original verdict.
	return verdict


# Regular expressions for server headers go here
ICY_FIELD_PATTERN = re.compile('Icy-|Ice-|X-Audiocast-')
ICY_VALUE_PATTERN = re.compile('icecast', re.IGNORECASE)

def handle_pre_response(url_info, url_record, response_info):
	url = url_info['url']

	# Check if server version starts with ICY
	if response_info.get('version', '') == 'ICY':
		maybe_log_ignore(url, '[icy version]')

		return wpull_hook.actions.FINISH

	# Loop through all the server headers for matches
	for field, value in response_info.get('fields', []):
		if ICY_FIELD_PATTERN.match(field):
			maybe_log_ignore(url, '[icy field]')

			return wpull_hook.actions.FINISH

		if field == 'Server' and ICY_VALUE_PATTERN.match(value):
			maybe_log_ignore(url, '[icy server]')

			return wpull_hook.actions.FINISH

	# Nothing matched, allow download
	return wpull_hook.actions.NORMAL


assert 2 in wpull_hook.callbacks.AVAILABLE_VERSIONS

wpull_hook.callbacks.version = 2
wpull_hook.callbacks.accept_url = accept_url
wpull_hook.callbacks.handle_pre_response = handle_pre_response
