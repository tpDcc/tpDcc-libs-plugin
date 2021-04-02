#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""
Module that contains implementations for Plugin Factory mechanism
"""

from __future__ import print_function, division, absolute_import

import os
import re
import sys
import inspect
import logging
from distutils import version

from tpDcc.libs.python import python, modules, path as path_utils, folder as folder_utils

logger = logging.getLogger('tpDcc-libs-python')


class PluginFactory(object):

    class PluginLoadingMechanism(object):
        """
        Class that contains variables used to define how the plugins on a registered path should be loaded
        """

        # Default mechanism. It will attempt to use the IMPORTABLE method first, and if the module is not
        # accessible from within sys modules it will fall back to LOAD_SOURCE.
        GUESS = 0

        # Mechanism to use when your plugin code is outside of the interpreter sys path. The plugin file
        # be loaded instead of imported. Gives flexibility in terms of structure but you cannot use
        # relative import paths within the plugins loaded with this mechanism. All loaded plugins using
        # this module are imported into a namespace defined through a uuid.
        LOAD_SOURCE = 1

        # Mechanism to use when your plugin code resides within already importable locations. Mandatory
        # to use when your plugin contains relative imports. Because this is importing modules which
        # are available on the sys.path, the class names will resolve nicely too
        IMPORTABLE = 2

    # Regex validator for plugin folder directories
    REGEX_FOLDER_VALIDATOR = re.compile('^((?!__pycache__).)*$')

    # Regex validator for plugin file names
    REGEX_FILE_VALIDATOR = re.compile(r'([a-zA-Z].*)(\.py$|\.pyc$)')

    def __init__(self, interface, paths=None, package_name=None, plugin_id=None, version_id=None, env_var=None):
        """

        :param interface: Abstract class to use when searching for plugins within the registered paths.
        :param paths: list(str), list of absolute paths to search for plugins.
        :param plugin_id: str, plugin identifier to distinguish between different plugins. If not given, plugin
            class name will be used
        :param version_id: str, plugin version identifier. If given, allows plugins with the same identifier to be
            differentiated.
        :param env_var: str, optional environment variable name containing paths to register separated by OS separator.
        """

        self._interface = interface
        self._plugin_identifier = plugin_id or '__name__'
        self._version_identifier = version_id

        self._plugins = dict()
        self._registered_paths = dict()

        self.register_paths(paths, package_name=package_name)
        if env_var:
            self.register_paths_from_env_var(env_var, package_name=package_name)

    def __repr__(self):
        return '[{} - Identifier: {}, Plugin Count: {}]'.format(
            self.__class__.__name__, self._plugin_identifier, len(self._plugins))

    # ============================================================================================================
    # BASE
    # ============================================================================================================

    def register_path(self, path, package_name=None, mechanism=PluginLoadingMechanism.GUESS):
        """
        Registers a search path within the factory. The factory will immediately being searching recursively withing
        this location for any plugin.
        :param path: str, absolute path to register into the factory
        :param package_name: str, package name current registered plugins will belong to. Default to tDcc.
        :param mechanism: PluginLoadingMechanism, plugin load mechanism to use
        :return: int, total amount of registered plugins
        """

        if not path or not os.path.isdir(path):
            return 0

        package_name = package_name or 'tpDcc'

        # Regardless of what is found in the given path, we store it
        self._registered_paths.setdefault(package_name, dict()).setdefault(path, dict())
        self._registered_paths[package_name][path] = mechanism

        current_plugins_count = len(self._plugins)

        file_paths = list()
        for root, _, files in folder_utils.walk_level(path):
            if not self.REGEX_FOLDER_VALIDATOR.match(root):
                continue

            for file_name in files:

                # Skip files that do not match PluginFactory regex validator.
                if not self.REGEX_FILE_VALIDATOR.match(file_name):
                    continue
                if file_name.startswith('test') or file_name in ['setup.py']:
                    continue

                file_paths.append(path_utils.clean_path(os.path.join(root, file_name)))

        # Loop through all the found files searching for plugins definitions
        for file_path in file_paths:

            module_to_inspect = None

            if mechanism in (self.PluginLoadingMechanism.IMPORTABLE, self.PluginLoadingMechanism.GUESS):
                module_to_inspect = self._mechanism_import(file_path)
                # if module_to_inspect:
                #     logger.debug('Module Import : {}'.format(file_path))

            if not module_to_inspect:
                if mechanism in (self.PluginLoadingMechanism.LOAD_SOURCE, self.PluginLoadingMechanism.GUESS):
                    module_to_inspect = self._mechanism_load(file_path)
                    # if module_to_inspect:
                    #     logger.debug('Direct Load : {}'.format(file_path))

            if not module_to_inspect:
                continue

            try:
                for item_name in dir(module_to_inspect):
                    item = getattr(module_to_inspect, item_name)
                    if inspect.isclass(item):
                        if item == self._interface:
                            continue
                        if issubclass(item, self._interface):
                            item.ROOT = path
                            item.PATH = file_path
                            self._plugins.setdefault(package_name, list())
                            self._plugins[package_name].append(item)
            except BaseException:
                logger.debug('', exc_info=True)

        return len(self._plugins) - current_plugins_count

    def register_paths(self, paths, package_name=None, mechanism=PluginLoadingMechanism.GUESS):
        """
        Registers given paths within the factory. The factory will immediately being searching recursively withing
        this location for any plugin.
        :param paths: list(str), absolute paths to register into the factory
        :param package_name: str, package name current registered plugins will belong to. Default to tDcc.
        :param mechanism: PluginLoadingMechanism, plugin load mechanism to use
        :return: int, total amount of registered plugins
        """

        paths = python.force_list(paths)

        total_plugins = 0
        visited = set()
        for path in paths:
            if not path:
                continue
            base_name = path_utils.clean_path(os.path.splitext(path)[0] if os.path.isfile(path) else path)
            if base_name in visited:
                continue
            visited.add(base_name)
            total_plugins += self.register_path(path, package_name=package_name, mechanism=mechanism)

        return total_plugins

    def register_paths_from_env_var(self, env_var, package_name=None, mechanism=PluginLoadingMechanism.GUESS):
        """
        Registers paths contained in given environment variables. Paths must be separated with OS separator
        :param env_var: str, environment variable we are going to retrieve paths from
        :param package_name: str, package name current registered plugins will belong to. Default to tDcc.
        :param mechanism: PluginLoadingMechanism, plugin load mechanism to use
        :return: int, total amount of registered plugins
        """

        paths = os.environ.get(env_var, '').split(os.pathsep)
        if not paths:
            return

        return self.register_paths(paths, package_name=package_name, mechanism=mechanism)

    def register_plugin_from_class(self, plugin_class, package_name=None):
        """
        Registers the given class type as a plugin for this factory. Note that the given type class must be inherited
        from the factory interface. Useful when you have direct access to the plugin classes without the need of
        searching disk locations (which is slow)
        :param plugin_class: type, class type to add to the factory
        :return: True if the registration is successful; False otherwise.
        """

        if not inspect.isclass(plugin_class) or not issubclass(plugin_class, self._interface):
            return False

        if not package_name:
            class_id = self._get_identifier(plugin_class)
            split_id = class_id.replace('.', '-').split('-')[0]
            package_name = split_id if split_id != class_id else 'tpDcc'

        self._plugins.setdefault(package_name, list).append(plugin_class)

        return True

    def paths(self, package_name=None):
        """
        Returns all registered paths in the factory
        :return: list(str)
        """

        return list(self._registered_paths.get(package_name, dict()).keys())

    def identifiers(self, package_name=None):
        """
        Returns a list of plugin class names within the factory. The list of class names is unique, so classes which
        share the same name will not appear twice.
        :param package_name: str, package name current registered plugins will belong to. Default to tDcc.
        :return: list(str)
        """

        package_name = package_name or 'tpDcc'
        return {
            self._get_identifier(plugin) for plugin in self._plugins.get(package_name, list())
        }

    def versions(self, identifier, package_name=None):
        """
        Returns a list of all the versions available for the plugins with the given identifier
        :param identifier: str, Plugin identifier to check
        :param package_name: str, package name current registered plugins will belong to. Default to tDcc.
        :return: list(str)
        """

        if not self._version_identifier:
            return list()

        return sorted(
            self._get_version(plugin) for plugin in self._plugins.get(
                package_name, list()) if self._get_identifier(plugin) == identifier
        )

    def plugins(self, package_name=None):
        """
        Returns a unique list of plugins. Where multiple versions are available the highest version will be given
        :param package_name: str, package name current registered plugins will belong to.
        :return: list(class)
        """

        return [self.get_plugin_from_id(
            identifier, package_name=package_name) for identifier in self.identifiers(package_name=package_name)]

    def get_plugin_from_id(self, plugin_id, package_name=None, plugin_version=None):
        """
        Retrieves the plugin with given plugin identifier. If you require a specific version of a plugin (in a
        scenario where there are multiple plugins with the same identifier) this can also be specified
        :param plugin_id: str, identifying value of the plugin you want to retrieve
        :param package_name: str, package name current registered plugins will belong to.
        :param plugin_version: int or float, version of the plugin you want. If factory has no versioning identifier
            specified this argument has no effect.
        :return: Plugin
        """

        if package_name and package_name not in self._plugins:
            logger.error('Impossible to retrieve data from id: {} package: "{}" not registered!'.format(
                plugin_id, package_name))
            return None

        if package_name:
            matching_plugins = [plugin for plugin in self._plugins.get(
                package_name, list()) if self._get_identifier(plugin) == plugin_id]
        else:
            matching_plugins = list()
            for plugins in list(self._plugins.values()):
                for plugin in plugins:
                    if self._get_identifier(plugin) == plugin_id:
                        matching_plugins.append(plugin)

        if not matching_plugins:
            logger.warning('No plugin with id "{}" found in package "{}"'.format(plugin_id, package_name))
            return None

        if not self._version_identifier:
            return matching_plugins[0]

        versions = {
            self._get_version(plugin): plugin for plugin in matching_plugins
        }
        ordered_versions = [version.LooseVersion(str(v)) for v in list(versions.keys())]

        # If not version given, we return the plugin with the highest value
        if not plugin_version:
            return versions[str(ordered_versions[0])]

        plugin_version = version.LooseVersion(plugin_version)
        if plugin_version not in ordered_versions:
            logger.warning('No Plugin with id "{}" and version "{}" found in package "{}"'.format(
                plugin_id, plugin_version, package_name))
            return None

        return versions[str(plugin_version)]

    def unregister_path(self, path, package_name=None):
        """
        Unregister given path from the list of registered paths
        :param path: Absolute path we want to unregister from registered factory paths
        :param package_name: str, package name current registered plugins will belong to. Default to tDcc.
        """

        registered_paths = self._registered_paths.copy()

        self._plugins = list()
        self._registered_paths = dict()

        for pkg_name, registered_paths_dict in registered_paths.items():
            for original_path, mechanism in registered_paths_dict.items():
                if package_name == pkg_name and path_utils.clean_path(original_path) == path_utils.clean_path(path):
                    continue
                self.register_path(original_path, package_name=pkg_name, mechanism=mechanism)

    def reload(self):
        """
        Clears all registered plugins and performs a search over all registered paths
        """

        registered_paths = self._registered_paths.copy()

        self.clear()

        for package_name, registered_paths_dict in registered_paths.items():
            for original_path, mechanism in registered_paths_dict.items():
                self.register_path(original_path, package_name=package_name, mechanism=mechanism)

    def clear(self):
        """
        Clears all the plugins and registered paths
        """

        self._plugins.clear()
        self._registered_paths.clear()

    # ============================================================================================================
    # INTERNAL
    # ============================================================================================================

    def _mechanism_import(self, file_path):
        """
        Internal function that will try to retrieve a module from a given path by looking current sys.path
        :param file_path: str, absolute file path of a Python file
        :return: module or None
        """

        # In Python 2 we check the existence of an __init__ file
        has_init = True
        if python.is_python2():
            has_init = False
            file_dir = os.path.dirname(file_path)
            for extension in ('.py', '.pyc'):
                if os.path.isfile(os.path.join(file_dir, '__init__{}'.format(extension))):
                    has_init = True
                    break
        if not has_init:
            return None

        module_name = modules.convert_to_dotted_path(file_path)
        if module_name:
            try:
                return sys.modules[module_name]
            except KeyError:
                return modules.import_module(module_name, skip_errors=True)

        return None

    def _mechanism_load(self, file_path):
        """
        Internal function that will try to retrieve a module by directly loading its source code
        :param file_path: str, absolute file path of a Python file
        :return: module or None
        """

        return modules.load_module_from_source(file_path)

    def _get_identifier(self, plugin):
        """
        Internal function that uses plugin identifier to request the identifying name of the plugin
        :param plugin: str, plugin to take name from
        :return: str
        """

        identifier = getattr(plugin, self._plugin_identifier)

        predicate = inspect.ismethod if python.is_python2() else inspect.isfunction
        if predicate(identifier):
            return identifier()

        return identifier

    def _get_version(self, plugin):
        """
        Internal function that uses plugin version identifier to request the version number of the plugin
        :param plugin: str, plugin to take version from
        :return: int or float
        """

        identifier = getattr(plugin, self._version_identifier)

        predicate = inspect.ismethod if python.is_python2() else inspect.isfunction
        if predicate(identifier):
            return str(identifier())

        return str(identifier)
