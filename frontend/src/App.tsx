import React, { useEffect, useState } from 'react';

import { FolderOutlined, ExperimentOutlined } from '@ant-design/icons';


import type { DataNode } from 'antd/es/tree';

import { Tree, Layout } from 'antd';

import { Typography, Space } from 'antd';


import * as Diff2Html from "diff2html";
import "diff2html/bundles/css/diff2html.min.css";

import './App.css';
import { sha1 } from 'crypto-hash'

const { Title } = Typography;

const { Header, Content, Sider } = Layout;
const { DirectoryTree } = Tree;


type DiffNodeProps = {
  status: string,
  linesAdded: number,
  linesRemoved: number,
  numChildren: number,
  numDirectChildren: number,
  isDirectory: boolean
};

type DiffNode = DataNode & Partial<DiffNodeProps>;

let DEMO = !(process.env.VMDIFF_DEMO === "false")
let BASE_URL = ""

// Serve from the cached /json directory if this is a demo, otherwise from the localhost server directly.
// It's always a demo, though.
if (DEMO) {
  BASE_URL = window.location.pathname + "json";
}


const colours: any = {
  added: "#52c41a",
  removed: "#eb2f96",
  modified: "#d0b44c",
  unchanged: "#333"
}

const initTreeData: DiffNode[] = [];

const getInitTreeData = (): Promise<DiffNode[]> => {

  return fetch(BASE_URL + "/changed_files").then((response) => {
    return response.json()
  });
}

const getChildrenData = (key: React.Key): Promise<DiffNode[]> => {

  if (DEMO) {
    const hasher = sha1(String(key))

    return hasher.then((hash) => {
      return fetch(BASE_URL + `/children/` + hash).then((response) => {
        return response.json()
      });
    });

  } else {
    return fetch(BASE_URL + `/children?` + new URLSearchParams({
      key: String(key)
    })).then((response) => {
      return response.json()
    });
  }
}
const getDiffString = (key: React.Key): Promise<string[]> => {

  if (DEMO) {
    const hasher = sha1(String(key))

    return hasher.then((hash) => {
      return fetch(BASE_URL + `/diff/` + hash).then((response) => {
        return response.json()
      });
    });

  } else {

    return fetch(BASE_URL + `/diff?` + new URLSearchParams({
      key: String(key)
    })).then((response) => {
      return response.json()
    });
  }
}

const treeMap = new Map<React.Key, DiffNode>();

const cache = (nodes: DiffNode[]): void => {
  nodes.map((node) => {
    treeMap.set(node.key, node)
    if (node.children) {
      cache(node.children)
    }
    return null
  })
}
// Cache the initial tree
cache(initTreeData);


const setIcon = (node: DiffNode): DiffNode => {
  if (node.isDirectory && node.isLeaf) {
    node.icon = <FolderOutlined />
  }
  return node

}
const iconifyAll = () => {
  treeMap.forEach((value, key) => {
    treeMap.set(key, setIcon(value));
  })
}

// It's just a simple demo. You can use tree map to optimize update perf.
function updateTreeData(
  list: DiffNode[],
  key: React.Key,
  children: DiffNode[]
): DiffNode[] {
  iconifyAll();
  return list.map((node) => {
    if (node.key === key) {
      return {
        ...node,
        children,
      };
    } else if (node.children) {
      return {
        ...node,
        children: updateTreeData(node.children, key, children),
      };
    }
    return node;
  });
}

const getDiffHtml = (key: React.Key): Promise<string> => {

  return getDiffString(key).then((diffLines) => {

    const unifiedDiffString = diffLines.join("");
    const diffHtml = Diff2Html.html(
      unifiedDiffString,
      {
        drawFileList: false,
        matching: "lines",
        outputFormat: "line-by-line",
        renderNothingWhenEmpty: false
      }
    );
    return diffHtml
  })

}

const App: React.FC = () => {
  const [treeData, setTreeData] = useState<DiffNode[] | undefined>(undefined);
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);
  const [, setLoadedKeys] = useState<React.Key[]>([]);
  const [autoExpandParent, setAutoExpandParent] = useState(true);
  const [diff, setDiff] = useState("");
  const [collapsed, setCollapsed] = useState(true);

  useEffect(() => {
    getInitTreeData().then((data) => {
      cache(data)
      iconifyAll()
      const newExpandedKeys: React.Key[] = []
      const newLoadedKeys: React.Key[] = []
      treeMap.forEach((value, key) => {
        newLoadedKeys.push(key)

        // Nodes to leave collapsed initially
        if (value.children !== undefined && value.children.length > 0) {

          // If all children are leaves
          let allChildrenLeaves = true
          for (const child of value.children) {
            if (!child.isLeaf) {
              allChildrenLeaves = false;
              break;
            }
          }

          if (!allChildrenLeaves && value.numDirectChildren! < 10 && newExpandedKeys.length < 1000) {
            newExpandedKeys.push(key)
          }
        }

      })
      setExpandedKeys(newExpandedKeys)
      setLoadedKeys(newLoadedKeys)
      setTreeData(data)
    })
  }, []);



  const onExpand = (expandedKeys: React.Key[], { node }: { expanded: boolean, node: DiffNode }): any => {

    setExpandedKeys(expandedKeys)
    setAutoExpandParent(false);
  }


  const shouldAutoExpand = (key: React.Key): boolean => {
    const node = treeMap.get(key);

    // Always expand if there are just empty folders underneath.
    if (node?.numChildren === 0) {
      return true;
    }
    if (node?.numDirectChildren! > 10) {
      return false;
    }
    // Does the key have all leaf children?
    if (node !== undefined && node.children?.every(child => { return child.isLeaf })) {
      // TODO: Find a way to measure how many nodes are showing, not expanded
      if ((treeMap.size + node.children!.length) < 20) {
        console.log(`(${expandedKeys.length}) allowing expand of ${key}`)
        return true;
      }
      console.log(` (${expandedKeys.length}) not expanding ${key}`)
    }
    return false;
  }

  const expand = (key: React.Key) => {
    if (!(key in expandedKeys)) {
      setExpandedKeys((prev) => [...prev, key]);
    }
  }

  const onSelect = (selectedKeys: React.Key[]): any => {
    const key = selectedKeys[0];

    getDiffHtml(key).then((html) => {
      setDiff(html);
    });

  }



  const onLoadData = ({ key, children }: any) =>
    new Promise<void>(resolve => {
      console.log(key)
      if (children != null && children.length > 0) {
        // Do nothing if the node has children already somehow (double expand?)
        resolve();
        return;
      }

      setTimeout(() => {
        // Load the children of this node.
        getChildrenData(key).then((children) => {
          cache(children)
          setTreeData(origin =>
            origin === undefined ? undefined :
              updateTreeData(origin, key, children)
          );
          children.forEach((child) => {
            if (!child.isLeaf && shouldAutoExpand(child.key)) {
              expand(child.key);
            }
          })
          resolve();
        })
        resolve();
      })
    });

  const renderTitle = (node: DiffNode): React.ReactNode | undefined => {
    const titleTextStyle = {
      color: colours[node.status!],
      filter: "brightness(0.8)"
    }
    const numChildrenStyle = {
      color: "#aaa",
      "marginLeft": "5px"
    }

    const linesAddedStyle = {
      color: colours["added"],
      filter: "brightness(0.55)"
    }
    const linesRemovedStyle = {
      color: colours["removed"],
      filter: "brightness(0.55)"
    }
    const linesChangedStyle = {
      "marginLeft": "0.3rem",
      opacity: "80%"
    }

    const showLineStats = (node.linesAdded !== 0 || node.linesRemoved !== 0) && !node.isDirectory

    return <span className="node-title">
      {/* {node.status === "added" ? <PlusSquareTwoTone twoToneColor={colours.added} /> : null}
          {node.status === "removed" ? <MinusSquareTwoTone twoToneColor={colours.removed} /> : null}
          {node.status === "modified" ? <RightSquareTwoTone twoToneColor={colours.modified} /> : null} */}
      <span className="node-name" style={titleTextStyle} >{String(node.title)}</span>
      {node.numChildren !== undefined && node.numChildren > 0 && !expandedKeys.includes(node.key) ? <span style={numChildrenStyle}>({node.numChildren})</span> : null}
      {showLineStats ? <span style={linesChangedStyle}>
        {node.linesAdded !== 0 ? <span style={linesAddedStyle}>+{node.linesAdded}</span> : null}{node.linesAdded !== 0 && node.linesRemoved !== 0 ? "," : null}
        {node.linesRemoved !== 0 ? <span style={linesRemovedStyle}>-{node.linesRemoved}</span> : null}
      </span>
        : null}
    </span>
  }

  return (<Layout>
    <Header style={{ position: 'sticky', top: 0, zIndex: 1, width: '100%' }}>
      <Space>
        <Typography>

          <Title level={2} style={{
            color: "#fff"
          }}>
            <Space>
              <ExperimentOutlined
                size={30}
              />
              🔥vmdiff🔥
            </Space>
          </Title>
        </Typography>
      </Space >

    </Header >
    <Layout hasSider className="site-layout" style={{}}>

      <Sider collapsible collapsed={collapsed} onCollapse={value => setCollapsed(value)}
        theme={"light"}
        collapsedWidth={"30vw"}
        width={"60vw"}
        style={{
          overflow: 'scroll',
          height: '100vh',
          marginBottom: '50px',
        }}>

        <div id="components-tree-demo-dynamic"
          style={{
            height: "100%"
          }}
        >
          <DirectoryTree
            loadData={onLoadData}
            expandedKeys={expandedKeys}
            treeData={treeData}
            onExpand={onExpand}
            onSelect={onSelect}
            titleRender={renderTitle}
            virtual={true}
            blockNode={false}
            autoExpandParent={autoExpandParent}
            defaultExpandParent={true}
            style={{
              height: "100%"
            }}
          />
        </div>

      </Sider>
      <Content style={{ margin: '24px 16px 0', overflow: 'initial' }}>

        <div className="site-layout-background" style={{ padding: 24, textAlign: 'center' }}>
          <div id="code-diff" dangerouslySetInnerHTML={{ __html: diff }}>
          </div>
        </div>
      </Content>
    </Layout>
  </Layout >

  )
};

export default App;

