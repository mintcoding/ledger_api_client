from django import http, VERSION
from django.conf import settings
from django.contrib.auth import login, logout, get_user_model
from django.db.models import signals
from django.utils.deprecation import MiddlewareMixin
import urllib.request, json
import urllib.parse
from django.contrib import messages
from confy import env
from django.http import Http404, HttpResponse, JsonResponse, HttpResponseRedirect

class SSOLoginMiddleware(MiddlewareMixin):

    def process_request(self, request):
        User = get_user_model()
        ENABLE_DJANGO_LOGIN=settings.ENABLE_DJANGO_LOGIN

        SESSION_EXPIRY_SSO = 3600
        if settings.SESSION_EXPIRY_SSO:
            SESSION_EXPIRY_SSO = settings.SESSION_EXPIRY_SSO

        if (request.path.startswith('/logout') or request.path.startswith('/ledger/logout')) \
                    and 'HTTP_X_LOGOUT_URL' in request.META and request.META['HTTP_X_LOGOUT_URL']:
            logout(request)
            return http.HttpResponseRedirect(request.META['HTTP_X_LOGOUT_URL'])

        if VERSION < (2, 0):
            user_auth = request.user.is_authenticated()
        else:
            try:
                user_auth = request.user.is_authenticated
                if user_auth is True:
                     pass
                     if ENABLE_DJANGO_LOGIN is True:
                         if 'HTTP_REMOTE_USER' in request.META:
                              if len(request.META['HTTP_REMOTE_USER']) > 3:
                                    response = HttpResponse("<center><h1 style='font-family: Arial, Helvetica, sans-serif;'>Error: SSO detected as enabled.  ENABLE_DJANGO_LOGIN should be set to False when sso is enabled.</h1><br></center><script></script>")
                                    return response 
                     else:
                         pass
                         if request.user.email.lower() != request.META['HTTP_REMOTE_USER'].lower():
                             response = HttpResponse("<center><h1 style='font-family: Arial, Helvetica, sans-serif;'>Wait one moment please...</h1><br><img src='/static/ledger_api/images/ajax-loader-spinner.gif'></center><script> location.reload();</script>")
                             response.delete_cookie('sessionid')
                             return response
            except:
                print ("user_auth request user does not exist")
                response = HttpResponse("<center><h1 style='font-family: Arial, Helvetica, sans-serif;'>Wait one moment please...</h1><br><img src='/static/ledger_api/images/ajax-loader-spinner.gif'></center><script> location.reload();</script>")
                response.delete_cookie('sessionid')
                return response


        #print ("AM I AUTH")
        #print (user_auth)
        if not user_auth and 'HTTP_REMOTE_USER' in request.META and request.META['HTTP_REMOTE_USER']:
            attributemap = {
                'username': 'HTTP_REMOTE_USER',
                'last_name': 'HTTP_X_LAST_NAME',
                'first_name': 'HTTP_X_FIRST_NAME',
                'email': 'HTTP_X_EMAIL',
            }

            for key, value in attributemap.items():
                if value in request.META:
                    attributemap[key] = request.META[value]

            if hasattr(settings, 'ALLOWED_EMAIL_SUFFIXES') and settings.ALLOWED_EMAIL_SUFFIXES:
                allowed = settings.ALLOWED_EMAIL_SUFFIXES
                if isinstance(settings.ALLOWED_EMAIL_SUFFIXES, basestring):
                    allowed = [settings.ALLOWED_EMAIL_SUFFIXES]
                if not any([attributemap['email'].lower().endswith(x) for x in allowed]):
                    return http.HttpResponseForbidden()

            exists_in_ledger = False
            if attributemap['email'] and User.objects.filter(email__iexact=attributemap['email']).exists():
                user = User.objects.filter(email__iexact=attributemap['email'])[0]
                exists_in_ledger = True
            else:
                user = User()

            # connect to ledger and align local cache account

            json_response = {}
            try:
                data = urllib.parse.urlencode(attributemap)
                data = data.encode('utf-8')
                with urllib.request.urlopen(settings.LEDGER_API_URL+"/ledgergw/remote/user/"+attributemap['email']+"/"+settings.LEDGER_API_KEY+"/", data) as url:
                      json_response = json.loads(url.read().decode())
            except Exception as e:
                print ("Error Connecting to Ledger GW")
                print (e)
                response = HttpResponse("<h1>Error Connecting to Ledger GW</h1>")
                return response


            if 'user' in json_response:
                attributemap['ledger_id'] = json_response['user']['ledgerid']
                attributemap['ledger_data'] = json_response['user']
                attributemap['is_superuser'] = json_response['user']['is_superuser']
                attributemap['is_staff'] = json_response['user']['is_staff']
                attributemap['ledger_groups'] = json_response['user']['groups']
            else:
                messages.error(request, 'Unable to Update User Information from Ledger')
            user.__dict__.update(attributemap)
            user.save()

            if exists_in_ledger is False:
                response = HttpResponse("<center><h1 style='font-family: Arial, Helvetica, sans-serif;'>Wait one moment please</h1><br><img src='/static/ledger_api/images/ajax-loader-spinner.gif'></center><script> location.reload();</script>")
                response.delete_cookie('sessionid')
                return response

            user.backend = 'django.contrib.auth.backends.ModelBackend'
            request.session.set_expiry(SESSION_EXPIRY_SSO)
            login(request, user)
