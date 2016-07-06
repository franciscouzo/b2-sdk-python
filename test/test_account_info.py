######################################################################
#
# File: test/test_account_info.py
#
# Copyright 2016 Backblaze Inc. All Rights Reserved.
#
# License https://www.backblaze.com/using_b2_code.html
#
######################################################################

import json
from nose import SkipTest
import os
import platform
import unittest

import six

from b2.account_info.upload_url_pool import UploadUrlPool
from b2.account_info.exception import CorruptAccountInfo, MissingAccountData

if not platform.system().lower().startswith('java'):
    # in Jython 2.7.1b3 there is no sqlite3
    from b2.account_info import SqliteAccountInfo

try:
    import unittest.mock as mock
except:
    import mock


class TestUploadUrlPool(unittest.TestCase):
    def setUp(self):
        self.pool = UploadUrlPool()

    def test_take_empty(self):
        self.assertEqual((None, None), self.pool.take('a'))

    def test_put_and_take(self):
        self.pool.put('a', 'url_a1', 'auth_token_a1')
        self.pool.put('a', 'url_a2', 'auth_token_a2')
        self.pool.put('b', 'url_b1', 'auth_token_b1')
        self.assertEqual(('url_a2', 'auth_token_a2'), self.pool.take('a'))
        self.assertEqual(('url_a1', 'auth_token_a1'), self.pool.take('a'))
        self.assertEqual((None, None), self.pool.take('a'))
        self.assertEqual(('url_b1', 'auth_token_b1'), self.pool.take('b'))
        self.assertEqual((None, None), self.pool.take('b'))

    def test_clear(self):
        self.pool.put('a', 'url_a1', 'auth_token_a1')
        self.pool.clear_for_key('a')
        self.pool.put('b', 'url_b1', 'auth_token_b1')
        self.assertEqual((None, None), self.pool.take('a'))
        self.assertEqual(('url_b1', 'auth_token_b1'), self.pool.take('b'))
        self.assertEqual((None, None), self.pool.take('b'))


class TestSqliteAccountInfo(unittest.TestCase):

    FILE_NAME = '/tmp/test_b2_account_info'

    def setUp(self):
        if platform.system().lower().startswith('java'):
            # in Jython 2.7.1b3 there is no sqlite3
            raise SkipTest()
        try:
            os.unlink(self.FILE_NAME)
        except:
            pass

    def tearDown(self):
        try:
            os.unlink(self.FILE_NAME)
        except BaseException:
            pass

    def test_account_info(self):
        account_info = self._make_info()
        account_info.set_auth_data(
            'account_id', 'account_auth', 'api_url', 'download_url', 100, 'app_key', 'realm'
        )

        info2 = self._make_info()
        self.assertEqual('account_id', info2.get_account_id())
        self.assertEqual('account_auth', info2.get_account_auth_token())
        self.assertEqual('api_url', info2.get_api_url())
        self.assertEqual('app_key', info2.get_application_key())
        self.assertEqual('realm', info2.get_realm())
        self.assertEqual(100, info2.get_minimum_part_size())

    def test_corrupted(self):
        """
        Test that a corrupted file will be replaced with a blank file.
        """
        with open(self.FILE_NAME, 'wb') as f:
            f.write(six.u('not a valid database').encode('utf-8'))

        try:
            self._make_info()
            self.fail('should have thrown CorruptAccountInfo')
        except CorruptAccountInfo:
            pass

    def test_convert_from_json(self):
        """
        Tests converting from a JSON account info file, which is what version
        0.5.2 of the command-line tool used.
        """
        data = dict(
            account_auth_token='auth_token',
            account_id='account_id',
            api_url='api_url',
            application_key='application_key',
            download_url='download_url',
            minimum_part_size=5000,
            realm='production'
        )
        with open(self.FILE_NAME, 'wb') as f:
            f.write(json.dumps(data).encode('utf-8'))
        account_info = self._make_info()
        self.assertEqual('auth_token', account_info.get_account_auth_token())

    def test_clear(self):
        account_info = self._make_info()
        account_info.set_auth_data(
            'account_id', 'account_auth', 'api_url', 'download_url', 100, 'app_key', 'realm'
        )
        self.assertEqual('account_id', self._make_info().get_account_id())
        account_info.clear()

        try:
            self._make_info().get_account_id()
            self.fail('should have raised MissingAccountData')
        except MissingAccountData:
            pass

    def test_clear_bucket_upload_data(self):
        account_info = self._make_info()
        account_info.put_bucket_upload_url('bucket-0', 'http://bucket-0', 'bucket-0_auth')
        account_info.clear_bucket_upload_data('bucket-0')
        self.assertEqual((None, None), account_info.take_bucket_upload_url('bucket-0'))

    def test_large_file_upload_urls(self):
        account_info = self._make_info()
        account_info.put_large_file_upload_url('file_0', 'http://file_0', 'auth_0')
        self.assertEqual(
            ('http://file_0', 'auth_0'), account_info.take_large_file_upload_url('file_0')
        )
        self.assertEqual((None, None), account_info.take_large_file_upload_url('file_0'))

    def test_clear_large_file_upload_urls(self):
        account_info = self._make_info()
        account_info.put_large_file_upload_url('file_0', 'http://file_0', 'auth_0')
        account_info.clear_large_file_upload_urls('file_0')
        self.assertEqual((None, None), account_info.take_large_file_upload_url('file_0'))

    def test_bucket(self):
        account_info = self._make_info()
        bucket = mock.MagicMock()
        bucket.name = 'my-bucket'
        bucket.id_ = 'bucket-0'
        self.assertEqual(None, account_info.get_bucket_id_or_none_from_bucket_name('my-bucket'))
        account_info.save_bucket(bucket)
        self.assertEqual(
            'bucket-0', account_info.get_bucket_id_or_none_from_bucket_name('my-bucket')
        )
        self.assertEqual(
            'bucket-0', self._make_info().get_bucket_id_or_none_from_bucket_name('my-bucket')
        )
        account_info.remove_bucket_name('my-bucket')
        self.assertEqual(None, account_info.get_bucket_id_or_none_from_bucket_name('my-bucket'))
        self.assertEqual(
            None, self._make_info().get_bucket_id_or_none_from_bucket_name('my-bucket')
        )

    def test_refresh_bucket(self):
        account_info = self._make_info()
        self.assertEqual(None, account_info.get_bucket_id_or_none_from_bucket_name('my-bucket'))
        bucket_names = {'a': 'bucket-0', 'b': 'bucket-1'}
        account_info.refresh_entire_bucket_name_cache(six.iteritems(bucket_names))
        self.assertEqual('bucket-0', account_info.get_bucket_id_or_none_from_bucket_name('a'))
        self.assertEqual('bucket-0', self._make_info().get_bucket_id_or_none_from_bucket_name('a'))

    def _make_info(self):
        """
        Returns a new StoredAccountInfo that has just read the data from the file.
        """
        return SqliteAccountInfo(file_name=self.FILE_NAME)
