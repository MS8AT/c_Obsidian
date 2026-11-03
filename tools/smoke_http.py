"""Network smoke test for an isolated CI container, never a user's live vault."""
import argparse
import base64
from http.cookies import SimpleCookie
import json
import secrets
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url',required=True)
    parser.add_argument('--host',default='obsidian.ms8at.by')
    args=parser.parse_args()
    cookie,csrf='',''
    checks=[]
    def call(path,method='GET',body=None,authenticated=True):
        headers={'Host':args.host}
        if authenticated and cookie:headers['Cookie']=cookie
        if csrf:headers['X-CSRF-Token']=csrf
        data=None
        if body is not None:
            headers['Content-Type']='application/json'
            data=json.dumps(body).encode()
        request=Request(args.base_url+path,method=method,data=data,headers=headers)
        try:
            with urlopen(request,timeout=30) as response:return response.status,response.read(),dict(response.headers)
        except HTTPError as exc:return exc.code,exc.read(),dict(exc.headers)
    def expect(name,result,status):
        if result[0]!=status:raise SystemExit(name+': unexpected HTTP status '+str(result[0]))
        checks.append({'check':name,'status':status,'result':'PASS'})
        return result
    expect('public health',call('/api/health'),200)
    expect('protected graph',call('/api/graph'),401)
    login=expect('login',call('/api/login','POST',{'username':'CiUser','password':'ci-only-disposable-password'}),200)
    parsed=SimpleCookie(login[2]['Set-Cookie'])
    cookie='obsidian_session='+parsed['obsidian_session'].value
    csrf=json.loads(expect('session',call('/api/session'),200)[1])['csrf']
    for path in ['/','/app.js','/style.css','/api/status','/api/graph','/api/openapi']:
        expect(path,call(path),200)
    name='CI-'+secrets.token_hex(5)+'.md'
    expect('create note',call('/api/notes','POST',{'path':name,'content':'# CI\n[[Home]]'}),201)
    expect('read note',call('/api/note?path='+name),200)
    expect('refuse overwrite',call('/api/notes','POST',{'path':name,'content':'overwrite'}),400)
    png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII='
    expect('import image',call('/api/images','POST',{'path':'assets/ci.png','base64':png}),201)
    result=expect('read image',call('/api/image?path=assets/ci.png'),200)
    if result[1]!=base64.b64decode(png):raise SystemExit('Image mismatch')
    expect('logout',call('/api/logout','POST'),200)
    expect('revoked session',call('/api/graph'),401)
    print(json.dumps({'result':'PASS','checks':checks}))


if __name__=='__main__':main()
