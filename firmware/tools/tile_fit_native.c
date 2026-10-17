// Offline implementation of tile_quality.py's palette-aware greedy medoids.
// Host only; never linked into RP firmware. Allocations are bounded by 960 tiles.
#include <stdint.h>
#include <stdlib.h>
#include <float.h>
#ifdef _WIN32
#define API __declspec(dllexport)
#else
#define API
#endif
// General host-side dictionary selection from caller-supplied visible costs.
API int tile_select_costs(int rows,int n,int limit,const float *cost,int *selected,int *assignment) {
    if(rows<1||rows>960||n<1||n>960||limit<1||limit>n)return -1;
    float *best=malloc(rows*sizeof(float));uint8_t *used=calloc(n,1);double *gains=malloc(n*sizeof(double));
    if(!best||!used||!gains){free(best);free(used);free(gains);return -2;}
    int first=0;double minimum=1e300;
    for(int j=0;j<n;j++){double sum=0;for(int i=0;i<rows;i++)sum+=cost[i*n+j];if(sum<minimum){minimum=sum;first=j;}}
    selected[0]=first;used[first]=1;
    for(int i=0;i<rows;i++)best[i]=cost[i*n+first];
    for(int s=1;s<limit;s++){
        int choice=-1;double maximum=-1;
        for(int j=0;j<n;j++)gains[j]=0;
        for(int i=0;i<rows;i++){const float *row=cost+i*n;float b=best[i];for(int j=0;j<n;j++){float d=b-row[j];if(d>0)gains[j]+=d;}}
        for(int j=0;j<n;j++)if(!used[j]&&gains[j]>maximum){maximum=gains[j];choice=j;}
        selected[s]=choice;used[choice]=1;
        for(int i=0;i<rows;i++)if(cost[i*n+choice]<best[i])best[i]=cost[i*n+choice];
    }
    for(int i=0;i<rows;i++){int jbest=0;for(int s=1;s<limit;s++)if(cost[i*n+selected[s]]<cost[i*n+selected[jbest]])jbest=s;assignment[i]=jbest;}
    free(best);free(used);free(gains);return 0;
}
API void tile_join(int count,const float *base,const float *colors,const float *target,const int64_t *palette,int *assignment){
    for(int round=0;round<3;round++)for(int parity=0;parity<2;parity++)
    for(int y=0;y<30;y++)for(int x=0;x<32;x++)if(((x+y)&1)==parity){
        int t=y*32+x,best=0;double minimum=1e300;
        for(int c=0;c<count;c++){
            double value=base[t*count+c];
            for(int side=0;side<4;side++){
                if((side==0&&x==0)||(side==1&&x==31)||(side==2&&y==0)||(side==3&&y==29))continue;
                int nb=t+(side==0?-1:side==1?1:side==2?-32:32);
                const float *a=colors+(palette[t]*count+c)*192,*b=colors+(palette[nb]*count+assignment[nb])*192;
                for(int k=0;k<8;k++){
                    int e=side==0?k*8:side==1?k*8+7:side==2?k:56+k;
                    int f=side==0?k*8+7:side==1?k*8:side==2?56+k:k;
                    for(int d=0;d<3;d++){
                        float diff=(a[e*3+d]-target[t*192+e*3+d])-(b[f*3+d]-target[nb*192+f*3+d]);
                        value+=2*(double)diff*diff;
                    }
                }
            }
            if(value<minimum){minimum=value;best=c;}
        }
        assignment[t]=best;
    }
}
API int tile_fit(int n,int limit,const uint8_t *patterns,const float *weights,
                 const double *colorcost,int *selected,int *assignment) {
    if(n<1 || n>960 || limit<1 || limit>n)return -1;
    size_t nn=(size_t)n*n;
    float *cost=malloc(4*nn*sizeof(float)),*weighted=malloc(nn*sizeof(float));
    float *best=malloc(n*sizeof(float)),*gain=malloc(n*sizeof(float));
    uint8_t *used=calloc(n,1);
    if(!cost||!weighted||!best||!gain||!used){free(cost);free(weighted);free(best);free(gain);free(used);return -2;}
    for(int i=0;i<n;i++)for(int j=0;j<n;j++) {
        float c[4]={0,0,0,0};
        for(int k=0;k<64;k++) {
            unsigned index=patterns[i*64+k]*4+patterns[j*64+k];
            for(int p=0;p<4;p++)c[p]=(float)((double)c[p]+colorcost[p*16+index]);
        }
        float v=0;
        for(int p=0;p<4;p++){cost[p*nn+i*n+j]=c[p];v+=c[p]*weights[p*n+i];}
        weighted[i*n+j]=v;
    }
    int first=0;float minimum=FLT_MAX;
    for(int j=0;j<n;j++) {
        float sum=0;for(int i=0;i<n;i++)sum+=weighted[i*n+j];
        if(sum<minimum){minimum=sum;first=j;}
    }
    selected[0]=first;used[first]=1;
    for(int i=0;i<n;i++)best[i]=weighted[i*n+first];
    for(int s=1;s<limit;s++) {
        for(int j=0;j<n;j++)gain[j]=0;
        for(int i=0;i<n;i++) {
            const float *row=weighted+i*n;float b=best[i];
            for(int j=0;j<n;j++){float d=b-row[j];if(d>0)gain[j]+=d;}
        }
        int choice=-1;float maximum=-1;
        for(int j=0;j<n;j++)if(!used[j] && gain[j]>maximum){maximum=gain[j];choice=j;}
        selected[s]=choice;used[choice]=1;
        for(int i=0;i<n;i++)if(weighted[i*n+choice]<best[i])best[i]=weighted[i*n+choice];
    }
    for(int p=0;p<4;p++)for(int i=0;i<n;i++) {
        int chosen=0;float minimum=cost[p*nn+i*n+selected[0]];
        for(int s=1;s<limit;s++)if(cost[p*nn+i*n+selected[s]]<minimum){minimum=cost[p*nn+i*n+selected[s]];chosen=s;}
        assignment[p*n+i]=selected[chosen];
    }
    free(cost);free(weighted);free(best);free(gain);free(used);return 0;
}
