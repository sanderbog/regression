#!/usr/bin/python
# Copyright 2008 Rene Rivera
# Distributed under the Boost Software License, Version 1.0.
# (See accompanying file LICENSE_1_0.txt or http://www.boost.org/LICENSE_1_0.txt)

import re
import optparse
import time
import xml.dom.minidom
from xml.sax.saxutils import unescape, escape
import os.path

#~ Process a bjam XML log into the XML log format for Boost result processing.
class BJamLog2Results:

    def __init__(self,args=None):
        opt = optparse.OptionParser(
            usage="%prog [options] input")
        opt.add_option( '--output',
            help="output file" )
        opt.add_option( '--runner',
            help="runner ID (e.g. 'Metacomm')" )
        opt.add_option( '--comment',
            help="an HTML comment file to be inserted in the reports" )
        opt.add_option( '--tag',
            help="the tag for the results" )
        opt.add_option( '--incremental',
            help="do incremental run (do not remove previous binaries)",
            action='store_true' )
        opt.add_option( '--platform' )
        opt.add_option( '--source' )
        opt.add_option( '--revision' )
        self.output = None
        self.runner = None
        self.comment='comment.html'
        self.tag='trunk'
        self.incremental=False
        self.platform=''
        self.source='SVN'
        self.revision=None
        self.input = []
        ( _opt_, self.input ) = opt.parse_args(args,self)
        self.results = xml.dom.minidom.parseString('''<?xml version="1.0" encoding="UTF-8"?>
<test-run
  source="%(source)s"
  runner="%(runner)s"
  timestamp=""
  platform="%(platform)s"
  tag="%(tag)s"
  run-type="%(run-type)s"
  revision="%(revision)s">
</test-run>
''' % {
            'source' : self.source,
            'runner' : self.runner,
            'platform' : self.platform,
            'tag' : self.tag,
            'run-type' : 'incremental' if self.incremental else 'full',
            'revision' : self.revision,
            } )
        
        self.test = {}
        self.target = {}
        self.parent = {}
        self.log = {}
        
        self.add_log()
        self.gen_output()
        
        #~ print self.test
        #~ print self.target
    
    def add_log(self):
        bjam_log = xml.dom.minidom.parse(self.input[0])
        self.x(bjam_log.documentElement)
    
    def gen_output(self):
        if self.output:
            out = open(self.output,'w')
        else:
            out = sys.stdout
        if out:
            self.results.writexml(out,encoding='utf-8')
    
    def tostring(self):
        return self.results.toxml('utf-8')
    
    def x(self, *context, **kwargs):
        node = None
        names = [ ]
        for c in context:
            if c:
                if not isinstance(c,xml.dom.Node):
                    suffix = '_'+c.replace('-','_').replace('#','_')
                else:
                    suffix = '_'+c.nodeName.replace('-','_').replace('#','_')
                    node = c
                names.append('x')
                names = map(lambda x: x+suffix,names)
        if node:
            for name in names:
                if hasattr(self,name):
                    return getattr(self,name)(node,**kwargs)
                else:
                    assert False, 'Unknown node type %s'%(name)
        return None
    
    #~ The single top-level build element...
    def x_build( self, node ):
        test_run = self.results.documentElement
        #~ Iterate over the sub-sections in a specific order to build up the
        #~ cross-reference information and the XML output.
        for type in ('timestamp','comment','test','targets','action'):
            items = self.x(node,type)
            #~ Any items generated by the processing are inteserted into the results.
            if items:
                for item in items:
                    if item:
                        test_run.appendChild(self.results.createTextNode("\n"))
                        test_run.appendChild(item)
        return None
    
    #~ The timestamp goes to the corresponding attribute in the result.
    def x_build_timestamp( self, node ):
        test_run = self.results.documentElement
        timestamp = self.get_child(self.get_child(node,tag='timestamp'),tag='#cdata-section').data.strip()
        test_run.setAttribute('timestamp',timestamp)
        return None
    
    #~ Comment file becomes a comment node.
    def x_build_comment( self, node ):
        comment = None
        if self.comment:
            comment_f = open(self.comment)
            if comment_f:
                comment = comment_f.read()
                comment_f.close()
        if not comment:
            comment = ''
        return [self.new_text('comment',comment)]
    
    #~ Tests are remembered for future reference.
    def x_build_test( self, node ):
        test_run = self.results.documentElement
        test_node = self.get_child(node,tag='test')
        while test_node:
            test_name = test_node.getAttribute('name')
            self.test[test_name] = {
                'library' : test_name.split('/',1)[0],
                'test-name' : test_name.split('/',1)[1],
                'test-type' : test_node.getAttribute('type').lower(),
                'test-program' : self.get_child_data(test_node,tag='source').strip(),
                'target' : self.get_child_data(test_node,tag='target').strip(),
                'info' : self.get_child_data(test_node,tag='info',strip=True)
                }
            #~ Add a lookup for the test given the test target.
            self.target[self.test[test_name]['target']] = test_name
            test_node = self.get_sibling(test_node.nextSibling,tag='test')
        return None
    
    #~ Process the target dependency DAG into an ancestry tree so we can look up
    #~ which top-level library and test targets specific build actions correspond to.
    def x_build_targets( self, node ):
        test_run = self.results.documentElement
        target_node = self.get_child(self.get_child(node,tag='targets'),tag='target')
        while target_node:
            name = self.get_child_data(target_node,tag='name').strip()
            path = self.get_child_data(target_node,tag='path').strip()
            jam_target = self.get_child_data(target_node,tag='jam-target').strip()
            #~ Map for jam targets to virtual targets.
            self.target[jam_target] = {
                'name' : name,
                'path' : path
                }
            #~ Create the ancestry.
            dep_node = self.get_child(self.get_child(target_node,tag='dependencies'),tag='dependency')
            while dep_node:
                child = self.get_data(dep_node).strip()
                child_jam_target = '<p%s>%s' % (path,child.split('//',1)[1])
                self.parent[child_jam_target] = jam_target
                #~ print "--- %s\n  ^ %s" %(jam_target,child_jam_target)
                dep_node = self.get_sibling(dep_node.nextSibling,tag='dependency')
            target_node = self.get_sibling(target_node.nextSibling,tag='target')
        return None
    
    #~ Given a build action log, process into the corresponding test log and
    #~ specific test log sub-part.
    def x_build_action( self, node ):
        test_run = self.results.documentElement
        action_node = self.get_child(node,tag='action')
        while action_node:
            name = self.get_child(action_node,tag='name')
            if name:
                name = self.get_data(name)
                #~ Based on the action, we decide what sub-section the log
                #~ should go into.
                action_type = None
                if re.match('[^%]+%[^.]+[.](compile)',name):
                    action_type = 'compile'
                elif re.match('[^%]+%[^.]+[.](link|archive)',name):
                    action_type = 'link'
                elif re.match('[^%]+%testing[.](capture-output)',name):
                    action_type = 'run'
                elif re.match('[^%]+%testing[.](expect-failure|expect-success)',name):
                    action_type = 'result'
                #~ print "+   [%s] %s %s :: %s" %(action_type,name,'','')
                if action_type:
                    #~ Get the corresponding test.
                    (target,test) = self.get_test(action_node,type=action_type)
                    #~ And the log node, which we will add the results to.
                    log = self.get_log(action_node,test)
                    #~ print "--- [%s] %s %s :: %s" %(action_type,name,target,test)
                    #~ Collect some basic info about the action.
                    result_data = "%(info)s\n\n%(command)s\n%(output)s\n" % {
                        'command' : self.get_action_command(action_node,action_type),
                        'output' : self.get_action_output(action_node,action_type),
                        'info' : self.get_action_info(action_node,action_type)
                        }
                    #~ For the test result status we find the appropriate node
                    #~ based on the type of test. Then adjust the result status
                    #~ acorrdingly. This makes the result status reflect the
                    #~ expectation as the result pages post processing does not
                    #~ account for this inversion.
                    action_tag = action_type
                    if action_type == 'result':
                        if re.match(r'^compile',test['test-type']):
                            action_tag = 'compile'
                        elif re.match(r'^link',test['test-type']):
                            action_tag = 'link'
                        elif re.match(r'^run',test['test-type']):
                            action_tag = 'run'
                    #~ The result sub-part we will add this result to.
                    result_node = self.get_child(log,tag=action_tag)
                    if not result_node:
                        #~ If we don't have one already, create it and add the result.
                        result_node = self.new_text(action_tag,result_data,
                            result='succeed' if action_node.getAttribute('status') == '0' else 'fail',
                            timestamp=action_node.getAttribute('start'))
                        log.appendChild(self.results.createTextNode("\n"))
                        log.appendChild(result_node)
                    else:
                        #~ For an existing result node we set the status to fail
                        #~ when any of the individual actions fail, except for result
                        #~ status.
                        if action_type != 'result':
                            result = result_node.getAttribute('result')
                            if action_node.getAttribute('status') != '0':
                                result = 'fail'
                        else:
                            result = 'succeed' if action_node.getAttribute('status') == '0' else 'fail'
                        result_node.setAttribute('result',result)
                        result_node.appendChild(self.results.createTextNode("\n"))
                        result_node.appendChild(self.results.createTextNode(result_data))
            action_node = self.get_sibling(action_node.nextSibling,tag='action')
        return self.log.values()
    
    #~ The command executed for the action. For run actions we omit the command
    #~ as it's just noise.
    def get_action_command( self, action_node, action_type ):
        if action_type != 'run':
            return self.get_child_data(action_node,tag='command')
        else:
            return ''
    
    #~ The command output.
    def get_action_output( self, action_node, action_type ):
        return self.get_child_data(action_node,tag='output',default='')
    
    #~ Some basic info about the action.
    def get_action_info( self, action_node, action_type ):
        info = ""
        #~ The jam action and target.
        info += "%s %s\n" %(self.get_child_data(action_node,tag='name'),
            self.get_child_data(action_node,tag='path'))
        #~ The timing of the action.
        info += "Time: (start) %s -- (end) %s -- (user) %s -- (system) %s\n" %(
            action_node.getAttribute('start'), action_node.getAttribute('end'),
            action_node.getAttribute('user'), action_node.getAttribute('system'))
        #~ And for compiles some context that may be hidden if using response files.
        if action_type == 'compile':
            define = self.get_child(self.get_child(action_node,tag='properties'),name='define')
            while define:
                info += "Define: %s\n" %(self.get_data(define,strip=True))
                define = self.get_sibling(define.nextSibling,name='define')
        return info
    
    #~ Find the test corresponding to an action. For testing targets these
    #~ are the ones pre-declared in the --dump-test option. For libraries
    #~ we create a dummy test as needed.
    def get_test( self, node, type = None ):
        target = self.get_child_data(node,tag='jam-target')
        base = self.target[target]['name']
        while target in self.parent:
            target = self.parent[target]
        #~ main-target-type is a precise indicator of what the build target is
        #~ proginally meant to be.
        main_type = self.get_child_data(self.get_child(node,tag='properties'),
            name='main-target-type',strip=True)
        if main_type == 'LIB' and type:
            lib = self.target[target]['name']
            if not lib in self.test:
                self.test[lib] = {
                    'library' : re.search(r'libs/([^/]+)',lib).group(1),
                    'test-name' : os.path.basename(lib),
                    'test-type' : 'lib',
                    'test-program' : os.path.basename(lib),
                    'target' : lib
                    }
            test = self.test[lib]
        else:
            test = self.test[self.target[self.target[target]['name']]]
        return (base,test)
    
    #~ Find, or create, the test-log node to add results to.
    def get_log( self, node, test ):
        target_directory = os.path.dirname(self.get_child_data(
            node,tag='path',strip=True))
        target_directory = re.sub(r'.*[/\\]bin[.]v2[/\\]','',target_directory)
        target_directory = re.sub(r'[\\]','/',target_directory)
        if not target_directory in self.log:
            self.log[target_directory] = self.new_node('test-log',
                library=test['library'],
                test_name=test['test-name'],
                test_type=test['test-type'],
                test_program=test['test-program'],
                toolset=self.get_toolset(node),
                target_directory=target_directory,
                show_run_output='true' if 'info' in test and test['info'] == 'always_show_run_output' else 'false')
        return self.log[target_directory]
    
    #~ The precise toolset from the build properties.
    def get_toolset( self, node ):
        toolset = self.get_child_data(self.get_child(node,tag='properties'),
            name='toolset',strip=True)
        toolset_version = self.get_child_data(self.get_child(node,tag='properties'),
            name='toolset-%s:version'%toolset,strip=True)
        return '%s-%s' %(toolset,toolset_version)
    
    #~ XML utilities...
    
    def get_sibling( self, sibling, tag = None, id = None, name = None ):
        n = sibling
        while n:
            found = True
            if tag and found:
                found = found and tag == n.nodeName
            if (id or name) and found:
                found = found and n.nodeType == xml.dom.Node.ELEMENT_NODE
            if id and found:
                if n.hasAttribute('id'):
                    found = found and n.getAttribute('id') == id
                else:
                    found = found and n.hasAttribute('id') and n.getAttribute('id') == id
            if name and found:
                found = found and n.hasAttribute('name') and n.getAttribute('name') == name
            if found:
                return n
            n = n.nextSibling
        return None
    
    def get_child( self, root, tag = None, id = None, name = None ):
        return self.get_sibling(root.firstChild,tag=tag,id=id,name=name)
    
    def get_data( self, node, strip = False, default = None ):
        data = None
        if node:
            if not data:
                data = self.get_child(node,tag='#text')
            if not data:
                data = self.get_child(node,tag='#cdata-section')
            if data:
                data = data.data if not strip else data.data.strip()
        if not data:
            data = default
        return data
    
    def get_child_data( self, root, tag = None, id = None, name = None, strip = False, default = None ):
        return self.get_data(self.get_child(root,tag=tag,id=id,name=name),strip=strip,default=default)
    
    def new_node( self, tag, *child, **kwargs ):
        result = self.results.createElement(tag)
        for k in kwargs.keys():
            if kwargs[k] != '':
                if k == 'id':
                    result.setAttribute('id',kwargs[k])
                elif k == 'klass':
                    result.setAttribute('class',kwargs[k])
                else:
                    result.setAttribute(k.replace('_','-'),kwargs[k])
        for c in child:
            if c:
                result.appendChild(c)
        return result
    
    def new_text( self, tag, data, **kwargs ):
        result = self.new_node(tag,**kwargs)
        data = data.strip()
        if len(data) > 0:
            result.appendChild(self.results.createTextNode(data))
        return result


if __name__ == '__main__': BJamLog2Results()
