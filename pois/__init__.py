import json
import os
import re
import socket
import socks
import tldextract
import chardet

###################################################
###################################################
###################################################

ROOT_DIR = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))


class Pois():
    tlds = []
    tlds_file_path = ROOT_DIR + '/tlds.json'

    def __init__(self, timeout=10, proxy_info=None):
        self.timeout = timeout
        self.tlds = self.load_tlds_file(self.tlds_file_path)
        self.proxy_info=proxy_info or {}

    ##################################
    ##################################

    def load_tlds_file(self, path):
        try:
            return json.loads(open(path, 'r').read())
        except Exception as err:
            raise TldsFileError('tld data file can not be load, %s, err: %s' % (self.tlds_file_path, str(err)))

    ##################################
    ##################################

    def update_tlds_file(self, new_tld):
        try:
            with open(self.tlds_file_path, 'w') as f:
                self.tlds.update(new_tld)
                f.write(json.dumps(self.tlds, indent=4))
        except Exception as err:
            raise TldsFileError('can not write to file, %s,err: %s' % (self.tlds_file_path, str(err)))

    ##################################
    ##################################

    def find_whois_server_for_tld(self, tld):
        whois_server = ''
        try:
            s = SocketPipeline(proxy_info=self.proxy_info)
            result = s.execute('%s\r\n' % tld, 'whois.iana.org', 43)
            whois_server = (re.findall("^.*whois:.*$", result, re.MULTILINE | re.IGNORECASE))[0].strip().split(':')[1].strip()
        except:
            pass

        if whois_server:
            self.update_tlds_file({tld: whois_server})
            return whois_server

        raise NoWhoisServerFoundError('no whois server found for %s' % tld)

    ##################################
    ##################################

    def fetch(self, domain, whois_server=None):
        # domain nomalization        
        domain = Domain.normalize(domain)
        domain_suffix = Domain.get_suffix(domain)
        # whois server for second level domains is same as top level domain for example whois server for .co.uk is same as whois server for .uk so we get the latter
        # and search in tlds.json
        tld = domain_suffix.split('.')[-1]
        whois_server = whois_server or self.tlds.get(tld) or self.find_whois_server_for_tld(tld)

        s = SocketPipeline(timeout=self.timeout, proxy_info=self.proxy_info)
        result = s.execute(query="%s\r\n" % domain, server=whois_server,port=43)

        try:
            registrar_whois_server = (re.findall("^.*whois server.*$", result, re.MULTILINE | re.IGNORECASE)or
                    re.findall("^.*registrar whois.*$", result, re.MULTILINE | re.IGNORECASE))[0].strip().split(':')[1].strip()

        except Exception:
            registrar_whois_server = None
        # sometimes Registrar WHOIS Server is present but empty like 1001mp3.biz
        # so we use the previous result
        if registrar_whois_server:
            result = s.execute(query="%s\r\n" % domain, server=registrar_whois_server, port=43)

        return result

        ###################################################
        ###################################################
        ###################################################


class SocketPipeline():

    def __init__(self, timeout=10, proxy_info=None):
        self.timeout = timeout
        ################
        # set proxy
        self.sanitized_proxy_info=self._sanitize_proxy_info(proxy_info)
        #################

    def _sanitize_proxy_info(self, proxy_info):

        sanitized_proxy_info = {'proxy_type':None,'addr':None,'port':None,'username':None,'password':None}
        proxy_info = proxy_info or {}

        if proxy_info.get('proxy_type') == 'http':
            sanitized_proxy_info['proxy_type'] = socks.HTTP
        elif proxy_info.get('proxy_type') == 'socks4':
            sanitized_proxy_info['proxy_type'] = socks.SOCKS4
        elif proxy_info.get('proxy_type') == 'sock5':
            sanitized_proxy_info['proxy_type'] = socks.SOCKS5
        elif proxy_info.get('proxy_type'):
            raise SocketBadProxyError('proxy type error')

        sanitized_proxy_info['addr']=proxy_info.get('addr')
        sanitized_proxy_info['port']=proxy_info.get('port')
        sanitized_proxy_info['username']=proxy_info.get('username')
        sanitized_proxy_info['password']=proxy_info.get('password')
        return sanitized_proxy_info

        #################

    def execute(self, query, server, port):
        try:
            s = socks.socksocket()
            s.set_proxy(**self.sanitized_proxy_info)
            s.settimeout(self.timeout)
            s.connect((server, port))
            s.send(query.encode('utf-8'))
            result = b''
            while True:
                chunk = s.recv(4096)
                result += chunk
                if not chunk: break
            # whois result encoding from some domains has problems in utf-8 so we ignore that characters, for ex whois result of `controlaltdelete.pt`
            try:
                decoded_result = result.decode('utf-8')
            except UnicodeDecodeError:
                result_encoding = chardet.detect(result)['encoding']
                decoded_result = result.decode(result_encoding)

            return decoded_result

        except (socks.ProxyConnectionError, socket.timeout):
            raise SocketTimeoutError('time out on quering %s' % query)
        except Exception as err:
            raise SocketError('error on quering %s, err: %s' % (query, str(err)))
        finally:
            s.close()

            ###################################################
            ###################################################
            ###################################################


class Domain():

    @staticmethod
    def normalize(domain):
        parsed_url = tldextract.extract(domain)
        domain = parsed_url.domain and parsed_url.domain + '.' + parsed_url.suffix
        if not domain: raise BadDomainError('no domain detected for {}'.format(domain))
        if not parsed_url.suffix: raise BadDomainError('no suffix detected for {}'.format(domain))
        return domain.lower()

    @staticmethod
    def get_suffix(domain):
        parsed_url = tldextract.extract(domain)
        return parsed_url.suffix

        ###################################################
        ###################################################
        ###################################################

class PoisError(Exception):
    pass


class TldsFileError(PoisError):
    pass


class BadDomainError(PoisError):
    pass


class NoWhoisServerFoundError(PoisError):
    pass

class SocketError(PoisError):
    pass


class SocketTimeoutError(SocketError):
    pass

class SocketBadProxyError(SocketError):
    pass
