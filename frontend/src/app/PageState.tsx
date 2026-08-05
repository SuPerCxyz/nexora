import { Button, Card, Empty, Result, Skeleton } from "antd";

import { InternalApiError } from "../api/client";

export function PageLoading() {
  return <Card aria-label="正在加载"><Skeleton active paragraph={{ rows: 6 }} /></Card>;
}

export function PageError({ error, retry }: { error: Error; retry?: () => void }) {
  const expired = error instanceof InternalApiError && error.status === 401;
  return (
    <Result
      status={expired ? "403" : "error"}
      title={expired ? "管理员会话已失效" : "页面数据加载失败"}
      subTitle={expired ? "请重新登录后继续。" : error.message}
      extra={expired
        ? <Button type="primary" href="/login">前往登录</Button>
        : retry && <Button type="primary" onClick={retry}>重新加载</Button>}
    />
  );
}

export function PageEmpty({ description }: { description: string }) {
  return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={description} />;
}
