# ==================================================================================================
# Copyright 2011 Twitter, Inc.
# --------------------------------------------------------------------------------------------------
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this work except in compliance with the License.
# You may obtain a copy of the License in the LICENSE file, or at:
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==================================================================================================

__author__ = 'jsirois'

import os
import subprocess

from twitter.common import log
from twitter.common.dirutil import safe_mkdir
from twitter.pants.tasks import Config, TaskError

_ID_BY_OS = {
  'linux': lambda release, machine: ('linux', machine),
  'darwin': lambda release, machine: ('darwin', release.split('.')[0]),
}


_PATH_BY_ID = {
  ('linux', 'x86_64'): [ 'linux', 'x86_64' ],
  ('linux', 'amd64'): [ 'linux', 'x86_64' ],
  ('linux', 'i386'): [ 'linux', 'i386' ],
  ('darwin', '9'): [ 'mac', '10.5' ],
  ('darwin', '10'): [ 'mac', '10.6' ],
  ('darwin', '11'): [ 'mac', '10.7' ],
}


def select_binary(base_path, version, name):
  """
    Selects a binary...
    Raises TaskError if no binary of the given version and name could be found.
  """
  # TODO(John Sirois): finish doc of the path structure expexcted under base_path
  sysname, _, release, _, machine = os.uname()
  os_id = _ID_BY_OS[sysname.lower()]
  if os_id:
    middle_path = _PATH_BY_ID[os_id(release, machine)]
    if middle_path:
      binary_path = os.path.join(base_path, *(middle_path + [version, name]))
      log.debug('Selected %s binary at: %s' % (name, binary_path))
      return binary_path
  raise TaskError('Cannot generate thrift code for: %s' % [sysname, release, machine])


def runjava(jvmargs=None, classpath=None, main=None, args=None):
  """Spawns a java process with the supplied configuration and returns its exit code."""
  cmd = ['java']
  if jvmargs:
    cmd.extend(jvmargs)
  if classpath:
    cmd.extend(('-cp' if main else '-jar', os.pathsep.join(classpath)))
  if main:
    cmd.append(main)
  if args:
    cmd.extend(args)
  log.debug('Executing: %s' % ' '.join(cmd))
  return subprocess.call(cmd)


def nailgun_profile_classpath(nailgun_task, profile, ivy_jar=None, ivy_settings=None):
  def nailgun_runner(classpath, main, args):
    nailgun_task.ng('ng-cp', *classpath)
    nailgun_task.ng(main, *args)

  return profile_classpath(
    profile,
    java_runner=nailgun_runner,
    config=nailgun_task.context.config,
    ivy_jar=ivy_jar,
    ivy_settings=ivy_settings
  )


def profile_classpath(profile, java_runner=None, config=None, ivy_jar=None, ivy_settings=None):
  # TODO(John Sirois): consider rework when ant backend is gone and there is no more need to share
  # path structure

  def call_java(classpath, main, args):
    runjava(classpath=classpath, main=main, args=args)
  java_runner = java_runner or call_java

  config = config or Config.load()

  profile_dir = config.get('ivy-profiles', 'workdir')
  profile_libdir = os.path.join(profile_dir, '%s.libs' % profile)
  profile_check = '%s.checked' % profile_libdir
  if not os.path.exists(profile_check):
    # TODO(John Sirois): refactor IvyResolve to share ivy invocation command line bits
    ivy_classpath = [ivy_jar] if ivy_jar else config.getlist('ivy', 'classpath')

    safe_mkdir(profile_libdir)
    ivy_settings = ivy_settings or config.get('ivy', 'ivy_settings')
    ivy_xml = os.path.join(profile_dir, '%s.ivy.xml' % profile)
    ivy_args = [
      '-settings', ivy_settings,
      '-ivy', ivy_xml,

      # TODO(John Sirois): this pattern omits an [organisation]- prefix to satisfy IDEA jar naming
      # needs for scala - isolate this hack to idea.py where it belongs
      '-retrieve', '%s/[artifact]-[revision](-[classifier]).[ext]' % profile_libdir,

      '-sync',
      '-symlink',
      '-types', 'jar',
      '-confs', 'default'
    ]
    java_runner(classpath=ivy_classpath, main='org.apache.ivy.Main', args=ivy_args)
    with open(profile_check, 'w'): pass # touch

  return [os.path.join(profile_libdir, jar) for jar in os.listdir(profile_libdir)]
